"""LangGraph Text-to-SQL 企业级子图。

架构：sql_classify → generate_sql → validate_sql (AST) → execute_sql
                                          ↑ 重试 ←────────┘(失败时)

作为 chat_agent 的 query_database 工具被调用，将自然语言转为安全 SQL。

安全模型（纵深防御）：
    1. 意图分类 (sql_classify)：out_of_scope 直接短路，不进 SQL 生成
    2. 表白名单：sqlglot AST 遍历所有 Table 节点，拒绝不在白名单的表
    3. 操作拦截：AST 检测 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE → 拒绝
    4. 自动 LIMIT：缺失 LIMIT 时追加 LIMIT 20，防止全表扫描
    5. 事务只读：SET TRANSACTION READ ONLY，数据库层面禁止写入
    6. 语句超时：SET LOCAL statement_timeout = '5000ms'，防慢查询
    7. RLS 支持：SET LOCAL app.current_user_id，配合行级安全策略

核心优化：
    - sqlglot AST 解析：100% 确定性安全拦截 + LIMIT 追加，零 Token 成本
    - 时间锚点注入：解决 LLM 对"昨天/上周"的日期幻觉
    - 思维链 (CoT)：输出 thought_process 提升复杂 SQL 准确率
    - 失败重试升级：前2次用 signal_model，第3次升级 report_model
    - 用户上下文注入：关注博主/标的列表注入 prompt，支持"我的 xxx"查询
"""
import pytz
from datetime import datetime
from typing import Literal, TypedDict

import sqlglot
from sqlglot import exp
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agents.llm import get_report_llm, get_signal_llm
from app.core.config import settings
from app.core.deps import SessionLocal
from app.memory.identity import normalize_user_id
from app.prompts import get_prompt
from app.services.trace_service import traced_node


# ============================================================
# 1. State 定义
# ============================================================

class SQLState(TypedDict):
    question: str
    user_id: str
    sub_intent: Literal["data_query", "schema_query", "out_of_scope", ""]
    generated_sql: str
    thought_process: str
    validation_error: str
    execution_error: str
    retry_count: int
    result: str
    _trace_conv_id: str


# ============================================================
# 2. Schema 上下文
# ============================================================

DB_SCHEMA_DDL = """
-- bloggers: 博主资料表
CREATE TABLE bloggers (
    id UUID PRIMARY KEY,
    handle VARCHAR(128) UNIQUE,     -- Twitter用户名
    name VARCHAR(256),              -- 昵称
    bio TEXT,                       -- 简介
    avatar_url VARCHAR(512),
    followers_count INTEGER,        -- 粉丝数
    following_count INTEGER,        -- 关注数
    tweets_count INTEGER,           -- 推文总数(Twitter平台)
    favorites_count INTEGER,        -- 点赞数
    market_focus TEXT[],            -- 关注市场
    credibility_score FLOAT,        -- 可信度评分(0-100)
    total_predictions INTEGER,      -- 已验证预测数
    correct_predictions FLOAT,      -- 正确预测得分
    location VARCHAR(256),
    verified BOOLEAN,
    protected BOOLEAN,
    joined_at TIMESTAMP,            -- Twitter注册时间
    created_at TIMESTAMP            -- 入库时间
);

-- tweets: 推文数据表
CREATE TABLE tweets (
    id UUID PRIMARY KEY,
    tweet_id VARCHAR(64) UNIQUE,    -- Twitter原始推文ID
    author_handle VARCHAR(128),     -- 博主用户名
    author_name VARCHAR(256),
    content TEXT,                    -- 推文内容
    published_at TIMESTAMP,         -- 发布时间
    metrics JSONB,                  -- {likes, retweets, replies}
    status VARCHAR(20),             -- pending/analyzed
    created_at TIMESTAMP            -- 入库时间
);

-- predictions: 预测记录表
CREATE TABLE predictions (
    id UUID PRIMARY KEY,
    analysis_id UUID,
    tweet_id UUID,
    blogger_handle VARCHAR(128),    -- 博主用户名
    ticker VARCHAR(64),             -- 标的代码(BTC, ETH等)
    sentiment VARCHAR(16),          -- bullish/bearish/neutral
    investment_horizon VARCHAR(16), -- short/medium/long/unknown
    published_at TIMESTAMP,
    verifiable_at TIMESTAMP,        -- 可验证时间
    verdict VARCHAR(16),            -- correct/partial/incorrect/NULL
    score FLOAT,                    -- 1.0/0.5/0.0/NULL
    verified_at TIMESTAMP,
    created_at TIMESTAMP
);

-- analysis_results: 分析结果表
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY,
    tweet_id UUID,
    analysis_type VARCHAR(32),      -- tweet_analysis/ticker_summary
    result JSONB,                   -- 分析结果JSON
    model_used VARCHAR(64),
    confidence FLOAT,
    batch_id UUID,
    created_at TIMESTAMP
);
"""

SCHEMA_SUMMARY = """可查询的表：
• bloggers — 博主资料（handle, name, bio, followers_count, credibility_score, location, verified, joined_at）
• tweets — 推文（tweet_id, author_handle, content, published_at, metrics[JSONB], status[pending/analyzed]）
• predictions — 预测记录（blogger_handle, ticker, sentiment[bullish/bearish/neutral], investment_horizon, verdict[correct/partial/incorrect], score）
• analysis_results — 分析结果（tweet_id, analysis_type, result[JSONB], model_used, confidence）"""


# ============================================================
# 3. 意图分类（结构化输出）
# ============================================================

class IntentResult(BaseModel):
    intent: Literal["data_query", "schema_query", "out_of_scope"]
    reasoning: str = Field(default="", description="简短说明分类理由")


@traced_node("sql_classify")
def sql_classify_node(state: SQLState) -> dict:
    question = state["question"]
    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(IntentResult)

    try:
        result = structured_llm.invoke([
            SystemMessage(content="判断用户问题的意图，以 json 格式输出。意图类型：data_query(查数据), schema_query(问表结构), out_of_scope(无法回答/修改数据)。"),
            HumanMessage(content=question),
        ])
        logger.info("[SQL] classify: {} | Q: {}", result.intent, question[:50])
        return {"sub_intent": result.intent}
    except Exception as e:
        logger.warning("[SQL] classify failed: {}, fallback to data_query", e)
        return {"sub_intent": "data_query"}


# ============================================================
# 4. SQL 生成（时间锚点 + CoT + 用户上下文）
# ============================================================

class SQLGenResult(BaseModel):
    sql: str = Field(description="生成的 PostgreSQL SELECT 语句。如果无法生成，留空。")
    thought_process: str = Field(default="", description="分步骤思考：1.意图理解 2.表关联 3.过滤条件 4.排序与限制")
    confidence: float = Field(default=0.8, description="0.0-1.0 之间的置信度", ge=0.0, le=1.0)


def _get_user_context(user_id: str) -> str:
    from app.memory.preferences import get_preferences
    from app.memory.profile import get_profile

    user_id = normalize_user_id(user_id)
    db = SessionLocal()
    try:
        prefs = get_preferences(db, user_id)
        profile = get_profile(db, user_id)
    finally:
        db.close()

    lines = []
    if prefs.get("watched_bloggers"):
        handles = ", ".join(f"'{h}'" for h in prefs["watched_bloggers"])
        lines.append(f"用户关注的博主 handle 列表: [{handles}]")
    if prefs.get("interested_tickers"):
        tickers = ", ".join(f"'{t}'" for t in prefs["interested_tickers"])
        lines.append(f"用户关注的标的列表: [{tickers}]")
    if profile.get("name"):
        lines.append(f"用户名字: {profile['name']}")
    return "\n".join(lines)


@traced_node("generate_sql")
def generate_sql_node(state: SQLState) -> dict:
    question = state["question"]
    user_id = normalize_user_id(state["user_id"])
    retry_count = state.get("retry_count", 0)

    tz = pytz.timezone("Asia/Shanghai")
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    system_prompt = get_prompt("sql/system", current_time=current_time, db_schema_ddl=DB_SCHEMA_DDL)

    user_ctx = _get_user_context(user_id)
    if user_ctx:
        system_prompt += get_prompt("sql/user_context", user_ctx=user_ctx)

    messages = [SystemMessage(content=system_prompt)]

    if retry_count > 0 and (state.get("validation_error") or state.get("execution_error")):
        error_msg = state.get("validation_error") or state.get("execution_error")
        messages.append(HumanMessage(
            content=f"上次 SQL 报错，请修正。\n错误: {error_msg}\n原 SQL: {state.get('generated_sql')}\n\n用户问题: {question}"
        ))
    else:
        messages.append(HumanMessage(content=question))

    llm = get_report_llm() if retry_count >= 2 else get_signal_llm()
    structured_llm = llm.with_structured_output(SQLGenResult)

    try:
        result = structured_llm.invoke(messages)
        logger.info("[SQL] generate (retry={}): {}", retry_count, result.sql[:100] if result.sql else "(empty)")
        return {
            "generated_sql": result.sql,
            "thought_process": result.thought_process,
            "validation_error": "",
            "execution_error": "",
        }
    except Exception as e:
        logger.error("[SQL] generate failed: {}", e)
        return {
            "generated_sql": "",
            "validation_error": f"LLM 生成失败: {e}",
            "retry_count": retry_count + 1,
        }


# ============================================================
# 5. AST 校验（sqlglot，替代正则与 LLM 审查）
# ============================================================

def _ast_validate_and_sanitize(
    sql: str,
    dialect: str = "postgres",
    max_limit: int = 20,
) -> tuple[bool, str, str]:
    """AST 解析 + 安全校验 + 自动追加 LIMIT。

    Returns:
        (is_valid, sanitized_sql, error_message)
    """
    if not sql or not sql.strip():
        return False, sql, "SQL 为空"

    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except sqlglot.errors.ParseError as e:
        return False, sql, f"SQL 语法解析错误: {str(e)[:200]}"

    dangerous_ops = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop,
        exp.Alter, exp.Create, exp.Command,
    )
    for node in parsed.walk():
        if isinstance(node, dangerous_ops):
            return False, sql, f"安全拦截: 检测到非法操作 ({type(node).__name__})"

    allowed_tables = set(settings.sql_allowed_tables)
    for table_node in parsed.find_all(exp.Table):
        table_name = table_node.name.lower()
        if table_name and table_name not in allowed_tables:
            return False, sql, f"安全拦截: 表 '{table_name}' 不在允许范围内（允许: {', '.join(sorted(allowed_tables))}）"

    if isinstance(parsed, exp.Select):
        if not parsed.args.get("limit"):
            parsed = parsed.limit(max_limit)

    safe_sql = parsed.sql(dialect=dialect)
    return True, safe_sql, ""


@traced_node("validate_sql")
def validate_sql_node(state: SQLState) -> dict:
    sql = state.get("generated_sql", "")
    retry_count = state.get("retry_count", 0)

    is_valid, safe_sql, error_msg = _ast_validate_and_sanitize(sql, max_limit=20)

    if not is_valid:
        logger.warning("[AST] 拦截: {}", error_msg)
        return {
            "validation_error": error_msg,
            "retry_count": retry_count + 1,
            "generated_sql": "",
        }

    return {"generated_sql": safe_sql, "validation_error": ""}


# ============================================================
# 6. 数据库执行（上下文管理器 + RLS）
# ============================================================

@traced_node("execute_sql")
def execute_sql_node(state: SQLState) -> dict:
    sql = state["generated_sql"]
    user_id = normalize_user_id(state["user_id"])
    retry_count = state.get("retry_count", 0)

    with SessionLocal() as db:
        try:
            db.execute(text(f"SET LOCAL app.current_user_id = '{user_id}'"))
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text(f"SET LOCAL statement_timeout = '{settings.sql_query_timeout}'"))

            result = db.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())

            if not rows:
                logger.info("[SQL] execute: 0 rows")
                return {"result": "查询执行成功，但未找到匹配的数据。", "execution_error": ""}

            logger.info("[SQL] execute: {} rows", len(rows))
            lines = [f"查询成功，返回 {len(rows)} 行数据：", ""]
            header = " | ".join(str(c) for c in columns)
            lines.append(header)
            lines.append("-" * len(header))
            for row in rows[:20]:
                lines.append(" | ".join(str(v) if v is not None else "-" for v in row))

            return {"result": "\n".join(lines), "execution_error": ""}

        except Exception as e:
            logger.error("[SQL] execute failed: {} | SQL: {}", e, sql)
            return {
                "execution_error": str(e)[:300],
                "retry_count": retry_count + 1,
                "result": "",
            }


# ============================================================
# 7. 终端节点
# ============================================================

@traced_node("return_schema")
def return_schema_node(state: SQLState) -> dict:
    return {"result": SCHEMA_SUMMARY}


@traced_node("clarify")
def clarify_node(state: SQLState) -> dict:
    return {"result": "抱歉，我目前只负责查询博主、推文和预测相关的数据，或解答数据库表结构问题。"}


@traced_node("exceed_limit")
def exceed_limit_node(state: SQLState) -> dict:
    error = state.get("validation_error") or state.get("execution_error") or "未知错误"
    retries = state.get("retry_count", 0)
    return {"result": f"无法生成有效查询（重试 {retries} 次后放弃）。\n最后错误: {error}\n\n建议换个问法或简化查询条件。"}


# ============================================================
# 8. 路由
# ============================================================

def route_by_sub_intent(state: SQLState) -> str:
    mapping = {
        "data_query": "generate_sql",
        "schema_query": "return_schema",
        "out_of_scope": "clarify",
    }
    return mapping.get(state["sub_intent"], "clarify")


def route_after_validation(state: SQLState) -> str:
    if state.get("validation_error"):
        if state.get("retry_count", 0) < settings.sql_max_retries:
            return "generate_sql"
        return "exceed_limit"
    return "execute_sql"


def route_after_execution(state: SQLState) -> str:
    if state.get("execution_error"):
        if state.get("retry_count", 0) < settings.sql_max_retries:
            return "generate_sql"
        return "exceed_limit"
    return END


# ============================================================
# 9. 构建图 & 对外接口
# ============================================================

def build_sql_agent(checkpointer=None):
    graph = StateGraph(SQLState)

    graph.add_node("sql_classify", sql_classify_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("return_schema", return_schema_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("exceed_limit", exceed_limit_node)

    graph.add_edge(START, "sql_classify")
    graph.add_conditional_edges("sql_classify", route_by_sub_intent, ["generate_sql", "return_schema", "clarify"])
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_conditional_edges("validate_sql", route_after_validation, ["execute_sql", "generate_sql", "exceed_limit"])
    graph.add_conditional_edges("execute_sql", route_after_execution)

    graph.add_edge("return_schema", END)
    graph.add_edge("clarify", END)
    graph.add_edge("exceed_limit", END)

    return graph.compile(checkpointer=checkpointer)


_sql_agent = None


def _get_sql_agent():
    global _sql_agent
    if _sql_agent is None:
        try:
            from app.memory.checkpointer import get_checkpointer
            _sql_agent = build_sql_agent(checkpointer=get_checkpointer())
        except (RuntimeError, Exception):
            _sql_agent = build_sql_agent()
    return _sql_agent


def run_sql_query(question: str, user_id: str, conversation_id: str = "") -> str:
    """chat_agent 调用入口，支持透传 user_id 用于 RLS。"""
    import uuid

    user_id = normalize_user_id(user_id)
    agent = _get_sql_agent()
    thread_id = f"sql_{user_id}_{uuid.uuid4().hex[:8]}"

    initial_state: SQLState = {
        "question": question,
        "user_id": user_id,
        "sub_intent": "",
        "generated_sql": "",
        "thought_process": "",
        "validation_error": "",
        "execution_error": "",
        "retry_count": 0,
        "result": "",
        "_trace_conv_id": conversation_id,
    }

    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(initial_state, config=config)
    return result.get("result", "查询处理异常")

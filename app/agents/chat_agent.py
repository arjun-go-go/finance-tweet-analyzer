"""聊天 Agent —— LangGraph ReAct + ToolNode 架构。

这是面向终端用户的对话智能体，通过工具链实现完整的金融数据工作流：
    采集博主资料 → 采集推文 → 触发 AI 分析 → 查询历史数据

企业级特性：
    - 递归限制 (recursion_limit=30)：防止无限工具调用循环
    - Token 预算：调用 LLM 前估算上下文大小，超限自动裁剪
    - 工具结果截断 (3000字符)：防止大结果撑爆上下文窗口
    - 用户隔离 (user_id)：通过 RunnableConfig metadata 全链路透传
    - 个性化 Prompt：注入用户档案 + 偏好（关注博主/标的/回复风格）
    - 工具熔断器 (@resilient_tool)：指数退避重试 + 三态熔断 + 降级消息
    - 偏好自动提取：对话结束后异步解析用户意图并更新偏好

图拓扑：
    START → init → mem0_recall → agent → (tool_calls?) → tools → agent → ... → extract_preferences → mem0_store → END
"""
import importlib.util
import re
import time
from functools import lru_cache
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool, InjectedToolArg
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.agents.llm import get_report_llm, get_signal_llm
from app.agents.chat.routing import (
    ANALYSIS_TOOL_NAMES as _ANALYSIS_TOOL_NAMES,
    INGEST_TOOL_NAMES as _INGEST_TOOL_NAMES,
    READ_ONLY_TOOL_NAMES as _READ_ONLY_TOOL_NAMES,
    REPORT_TOOL_NAMES as _REPORT_TOOL_NAMES,
    classify_tool_route as _base_classify_tool_route,
    has_explicit_ingest_confirmation as _base_has_explicit_ingest_confirmation,
    has_explicit_report_confirmation as _base_has_explicit_report_confirmation,
    latest_human_text as _base_latest_human_text,
)
from app.agents.chat.tool_results import (
    parse_tool_envelope as _base_parse_tool_envelope,
    tool_error as _base_tool_error,
    tool_ok as _base_tool_ok,
    truncate_result as _truncate_tool_result,
)
from app.agents.chat.tools.ingestion import (
    fetch_profile_impl as _fetch_profile_impl,
    fetch_tweets_impl as _fetch_tweets_impl,
)
from app.agents.chat.tools.reports import (
    generate_tracking_report_impl as _generate_tracking_report_impl,
)
from app.agents.chat.tools.analysis_jobs import (
    confirm_tweet_analysis_impl as _confirm_tweet_analysis_impl,
    preview_tweet_analysis_impl as _preview_tweet_analysis_impl,
)
from app.agents.chat.tools.user_resources import (
    list_my_followed_bloggers_impl as _list_my_followed_bloggers_impl,
    list_my_tracked_tickers_impl as _list_my_tracked_tickers_impl,
)
from app.agents.chat.tools.rag_search import (
    search_my_documents_impl as _search_my_documents_impl,
    search_public_signals_impl as _search_public_signals_impl,
)
from app.agents.chat.nodes.context import (
    init_context_node_impl as _init_context_node_impl,
)
from app.agents.chat.nodes.memory import (
    extract_preferences_node_impl as _extract_preferences_node_impl,
    mem0_recall_node_impl as _mem0_recall_node_impl,
    mem0_store_node_impl as _mem0_store_node_impl,
)
from app.core.config import settings
from app.core.deps import SessionLocal
from app.core.resilience import resilient_tool
from app.memory.mem0_client import get_mem0_client
from app.memory.identity import normalize_user_id
from app.prompts import get_prompt


# ============================================================
# Agent State —— 自定义状态承载用户上下文
# ------------------------------------------------------------
# 在图入口加载一次用户档案/偏好，全图复用，避免每次工具调用
# 循环都重复查询 DB（消除 N+1 查询）。
# ============================================================

class AgentState(MessagesState):
    user_profile: dict
    user_prefs: dict
    consecutive_tool_failures: int = 0  # 追踪连续工具失败次数，防止死循环
    memories: list  # mem0 本轮召回的跨会话记忆
    tool_route: str = "read_only"
    allowed_tool_names: list[str]


# ============================================================
# 参数校验工具 —— 正则约束
# ------------------------------------------------------------
# 工具入口校验 LLM 传入参数，违规时返回错误信息触发自纠正。
# ============================================================

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_SINCE_RE = re.compile(r"^\d+[dwh]$")


def _get_authenticated_user_id(config: RunnableConfig | None) -> str:
    user_id = ((config or {}).get("metadata") or {}).get("user_id")
    return normalize_user_id(user_id)


@lru_cache(maxsize=1)
def _is_mem0_spacy_model_available() -> bool:
    """Return whether mem0 can run BM25 lemmatization without runtime downloads."""
    return importlib.util.find_spec("en_core_web_sm") is not None


# ============================================================
# Token 预算工具
# ------------------------------------------------------------
# 粗估算法：中英混合文本约 4 字符/token（保守估计）。
# 用于决定是否需要裁剪历史消息避免超出 LLM 上下文窗口。
# ============================================================

def _estimate_tokens(messages: list) -> int:
    """Rough token estimation: ~4 chars per token for mixed CN/EN."""
    total_chars = sum(
        len(m.content) if hasattr(m, "content") and isinstance(m.content, str) else 100
        for m in messages
    )
    return total_chars // 4


def _truncate_result(text: str, max_chars: int | None = None) -> str:
    """Truncate tool output to prevent context overflow."""
    limit = max_chars or settings.agent_tool_result_max_chars
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(结果已截断，原始长度 {len(text)} 字符)"


def _current_user_message(config: RunnableConfig | None) -> str:
    return str(((config or {}).get("metadata") or {}).get("current_message") or "")


def _has_explicit_report_confirmation(message: str, ticker: str) -> bool:
    text = message.lower()
    ticker_text = ticker.lower()
    action_words = ("确认", "立即", "开始", "执行", "生成", "创建", "确认生成", "go ahead", "confirm")
    report_words = ("报告", "周报", "跟踪报告", "report")
    return (
        ticker_text in text
        and any(word in text for word in action_words)
        and any(word in text for word in report_words)
    )


def _has_explicit_ingest_confirmation(
    message: str,
    *,
    handle: str,
    target_words: tuple[str, ...],
) -> bool:
    text = message.lower()
    handle_text = handle.lower().lstrip("@")
    action_words = ("确认", "立即", "开始", "执行", "获取", "抓取", "采集", "同步", "拉取", "fetch", "crawl", "confirm")
    return (
        handle_text in text
        and any(word in text for word in action_words)
        and any(word.lower() in text for word in target_words)
    )


# ============================================================
# 工具参数 Schema（Pydantic）—— 约束 LLM 生成的参数
# ------------------------------------------------------------
# 通过 args_schema 将参数约束转换为 JSON Schema 供 LLM 参考，
# 从源头减少参数格式错误。field_validator 在工具调用前执行，
# 验证失败会返回清晰的错误消息给 LLM，触发自纠正。
# ============================================================

_tool_ok = _base_tool_ok
_tool_error = _base_tool_error
_parse_tool_envelope = _base_parse_tool_envelope
_has_explicit_report_confirmation = _base_has_explicit_report_confirmation
_has_explicit_ingest_confirmation = _base_has_explicit_ingest_confirmation


class FetchProfileArgs(BaseModel):
    """获取博主资料的参数约束。"""
    blogger_handle: str = Field(
        description="纯英文/数字用户名（不含 @），1-15 位。例如 'elonmusk'。禁止中文或带 @。"
    )

    @field_validator("blogger_handle")
    @classmethod
    def _validate_handle(cls, v: str) -> str:
        v = v.strip().lstrip("@")
        if not re.match(r"^[A-Za-z0-9_]{1,15}$", v):
            raise ValueError(f"Handle '{v}' 无效。必须是 1-15 位纯英文/数字/下划线，不含 @。")
        return v


class FetchTweetsArgs(BaseModel):
    """采集推文的参数约束。"""
    blogger_handle: str = Field(
        description="纯英文/数字用户名（不含 @），1-15 位。例如 'elonmusk'。禁止中文或带 @。"
    )
    pages: int = Field(default=1, ge=1, le=3, description="抓取页数，限制 1-3 页。")

    @field_validator("blogger_handle")
    @classmethod
    def _validate_handle(cls, v: str) -> str:
        v = v.strip().lstrip("@")
        if not re.match(r"^[A-Za-z0-9_]{1,15}$", v):
            raise ValueError(f"Handle '{v}' 无效。必须是 1-15 位纯英文/数字/下划线，不含 @。")
        return v


class PreviewAnalysisArgs(BaseModel):
    """预览分析任务的参数约束。"""
    blogger_handle: str = Field(
        default="",
        description="指定博主英文 Handle（不含 @）。留空或 'all' 表示所有博主。禁止中文。",
    )
    reanalyze: bool = Field(default=False, description="True=重新分析已分析过的推文，False=仅分析新推文。")
    since: str = Field(
        default="",
        description="时间范围，必须严格匹配 '^\\d+[dwh]$'。例如 '3d'(3天)、'1w'(1周)、'12h'(12小时)。禁止自然语言。",
    )

    @field_validator("blogger_handle")
    @classmethod
    def _validate_handle(cls, v: str) -> str:
        v = v.strip().lstrip("@").lower()
        if v and v not in ("all", "全部", "所有") and not re.match(r"^[A-Za-z0-9_]{1,15}$", v):
            raise ValueError(f"Handle '{v}' 无效。必须是纯英文/数字，或留空/传 'all'。")
        return v

    @field_validator("since")
    @classmethod
    def _validate_since(cls, v: str) -> str:
        if v and not re.match(r"^\d+[dwh]$", v):
            raise ValueError(f"时间格式 '{v}' 错误。必须使用如 '3d'、'1w'、'12h' 的格式。")
        return v


class ConfirmTaskArgs(BaseModel):
    """确认分析任务的参数约束。"""
    task_id: str = Field(description="preview_tweet_analysis 返回的 8 位任务 ID。不要编造。")

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("task_id 不能为空。")
        return v


class TrackingReportArgs(BaseModel):
    """生成追踪报告的参数约束。"""
    ticker: str = Field(description="金融标的代码，如 TSLA、BTC、ETH。")
    time_range: str = Field(
        default="1w",
        description="时间范围：1d(1天)、1w(1周)、1m(1月)。",
    )

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("ticker 不能为空。")
        return v


# ============================================================
# 工具定义
# ------------------------------------------------------------
# 每个工具通过 @resilient_tool 装饰器获得：
#   - 指数退避重试（retries=3, backoff_base=2.0）
#   - 熔断器保护（连续失败5次 → 熔断120s → 半开探测）
#   - 降级消息（熔断期间直接返回友好提示，不调用下游）
# 内部实现函数 (_*_impl) 与对外工具函数分离，
# 实现熔断粒度控制（同一 circuit_name 共享熔断状态）。
# ============================================================



@tool(args_schema=FetchProfileArgs)
def fetch_and_save_profile(blogger_handle: str, config: RunnableConfig = None) -> str:
    """获取 Twitter 博主的最新基础资料（粉丝数、简介、推文数等）并保存到本地数据库。

    【触发场景】：用户首次提及某个博主，或要求查看某人的"主页信息""粉丝数""简介""个人资料"时使用。
    【参数规范】：blogger_handle 必须是纯英文/数字用户名（不含 @），1-15 位。切勿传入中文！例如 "elonmusk" 而非 "@elonmusk" 或 "马斯克"。
    【与其他工具边界】：仅采集博主资料，不抓推文。需要推文用 fetch_and_save_tweets。
    """
    from app.schemas.blogger import BloggerProfile
    from app.services.blogger_service import upsert_blogger
    from app.services.twitter_service import convert_profile_to_upsert

    handle = blogger_handle.strip().lstrip("@")
    if not handle:
        return "请提供博主用户名。"
    if not _HANDLE_RE.match(handle):
        return f"参数错误：'{blogger_handle}' 不是有效的 Twitter Handle。请提供纯英文/数字用户名（不含@，1-15位），例如 elonmusk。"

    if not _has_explicit_ingest_confirmation(
        _current_user_message(config),
        handle=handle,
        target_words=("资料", "主页", "profile", "简介", "粉丝"),
    ):
        return _tool_error(
            "CONFIRMATION_REQUIRED",
            f"获取并保存 @{handle} 资料会调用外部 Twitter API 并写入数据库。请明确回复：确认获取 {handle} 资料。",
            retryable=False,
        )

    logger.info("[Tool] fetch_and_save_profile: {}", handle)
    result = _fetch_profile_impl(handle)

    if isinstance(result, str) and result.startswith("["):
        return result

    if result is None:
        return f"未找到用户 @{handle}，可能用户不存在、账号受保护或网络异常。"

    upsert_data = convert_profile_to_upsert(result)
    profile = BloggerProfile(**upsert_data)

    db = SessionLocal()
    try:
        upsert_blogger(db, profile)
        db.commit()
        return (
            f"成功获取并保存 @{handle} 的资料。"
            f"昵称: {result.get('name', '')}, "
            f"粉丝: {result.get('followers', 0)}, "
            f"推文数: {result.get('tweets_count', 0)}, "
            f"简介: {result.get('description', '')[:100]}"
        )
    except Exception as e:
        db.rollback()
        return f"保存失败: {str(e)}"
    finally:
        db.close()


@tool(args_schema=FetchTweetsArgs)
def fetch_and_save_tweets(blogger_handle: str, pages: int = 1, config: RunnableConfig = None) -> str:
    """采集指定 Twitter 博主的最新推文并入库。

    【触发场景】：用户明确要求查看某人的"最新推文""刚刚发的推特""最近发了什么""今天的动态"等实时数据需求时使用。
    【参数规范】：blogger_handle 必须是纯英文/数字 Handle（不含 @），1-15 位，禁止传中文。pages 为抓取页数，限制 1-3。
    【前置条件】：需先确保博主已入库（已调用过 fetch_and_save_profile）。
    【与其他工具边界】：用于"抓取最新数据"，如果用户问"历史推文""统计""有哪些推文"，应使用 query_database 查本地库。
    """
    from sqlalchemy import select

    from app.models.blogger import Blogger
    from app.schemas.tweet import TweetImportItem
    from app.services.tweet_service import import_tweets
    from app.services.twitter_service import convert_tweets_to_import

    handle = blogger_handle.strip().lstrip("@")
    if not handle:
        return "请提供博主用户名。"
    if not _HANDLE_RE.match(handle):
        return f"参数错误：'{blogger_handle}' 不是有效的 Twitter Handle。请提供纯英文/数字用户名（不含@，1-15位）。"
    pages = max(1, min(pages, 3))

    if not _has_explicit_ingest_confirmation(
        _current_user_message(config),
        handle=handle,
        target_words=("推文", "tweets", "tweet", "最新推文"),
    ):
        return _tool_error(
            "CONFIRMATION_REQUIRED",
            f"抓取 @{handle} 最新推文会调用外部 Twitter API 并写入数据库。请明确回复：确认抓取 {handle} 最新推文。",
            retryable=False,
        )

    logger.info("[Tool] fetch_and_save_tweets: {} (pages={})", handle, pages)

    db = SessionLocal()
    try:
        blogger = db.execute(
            select(Blogger).where(Blogger.handle == handle)
        ).scalar_one_or_none()
        if not blogger or not blogger.twitter_user_id:
            return f"博主 @{handle} 尚未入库或缺少 user_id。请先调用 fetch_and_save_profile 获取资料。"
        user_id = blogger.twitter_user_id
    finally:
        db.close()

    raw_tweets = _fetch_tweets_impl(user_id, pages)

    if isinstance(raw_tweets, str) and raw_tweets.startswith("["):
        return raw_tweets

    if not raw_tweets:
        return f"未获取到 @{handle} 的推文，可能是账号受保护或暂无新推文。"

    original_count = sum(1 for t in raw_tweets if not t.get("is_retweet"))
    retweet_count = len(raw_tweets) - original_count

    import_items = convert_tweets_to_import(raw_tweets)
    tweet_models = [TweetImportItem(**item) for item in import_items]

    db = SessionLocal()
    try:
        imported, skipped = import_tweets(db, tweet_models)
        return (
            f"推文采集完成：共获取 {len(raw_tweets)} 条（原创 {original_count}，转推 {retweet_count}）。"
            f"入库：新导入 {imported} 条，跳过 {skipped} 条（已存在）。"
        )
    except Exception as e:
        db.rollback()
        return f"推文保存失败: {str(e)}"
    finally:
        db.close()




@resilient_tool(
    retries=2,
    backoff_base=1.0,
    circuit_name="sql_agent",
    failure_threshold=3,
    recovery_timeout=30.0,
    fallback_message="数据库查询服务暂时不可用，请稍后重试。",
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)
def _query_database_impl(query: str, user_id: str, conversation_id: str = "") -> str:
    from app.agents.sql_agent import run_sql_query
    return run_sql_query(query, user_id=user_id, conversation_id=conversation_id)


@tool
def query_database(natural_language_query: str, config: RunnableConfig) -> str:
    """查询本地数据库中已存在的历史数据（博主列表、推文统计、预测结果、分析详情等）。

    【触发场景】：用户询问"有哪些博主""粉丝最多的是谁""分析结果""历史预测""推文统计""xxx 的预测正确率""标的分析"等查询/统计需求。支持自然语言查询。
    【参数规范】：natural_language_query 是用户的原始查询语句，可以是中文，由 SQL Agent 自动转换为 SQL 执行。长度限制 500 字符，超长会被截断。
    【与其他工具边界】：用于"查本地历史数据"。如果用户要"抓取最新的"实时数据，应使用 fetch_and_save_profile 或 fetch_and_save_tweets。
    """
    # 防止超长查询撑爆上下文窗口或 SQL Agent
    max_query_len = 500
    original_len = len(natural_language_query)
    if original_len > max_query_len:
        natural_language_query = natural_language_query[:max_query_len]
        logger.warning("[Tool] query_database: query truncated from {} to {} chars", original_len, max_query_len)

    user_id = _get_authenticated_user_id(config)
    thread_id = (config.get("metadata") or {}).get("thread_id", "")
    logger.info("[Tool] query_database: user={} q={}", user_id, natural_language_query[:50])
    result = _query_database_impl(natural_language_query, user_id=user_id, conversation_id=thread_id)
    if isinstance(result, str) and result.startswith("["):
        return result
    return _truncate_result(result)


# ============================================================
# 工具注册 & ToolNode
# ------------------------------------------------------------
# handle_tool_errors=True：工具抛异常时返回错误消息给 Agent，
# 而非终止整个图执行，让 Agent 有机会重试或换策略。
# ============================================================

@tool(args_schema=TrackingReportArgs)
def generate_tracking_report(
    ticker: str,
    time_range: str = "1w",
    config: RunnableConfig = None,
) -> str:
    """生成指定金融标的的跟踪报告（基于 RAG 多路召回 + Rerank + LLM 合成）。

    【触发场景】：用户要求生成报告、分析某个标的的最近动态、周报等。
    【参数】：ticker 为标的代码（如 TSLA、BTC），time_range 为时间范围（1d/1w/1m）。
    """
    from uuid import UUID

    user_id_value = ((config or {}).get("metadata") or {}).get("user_id")
    try:
        user_id = UUID(user_id_value)
    except (TypeError, ValueError, AttributeError):
        return "用户身份无效，无法生成私有报告。"

    if not _has_explicit_report_confirmation(_current_user_message(config), ticker):
        return _tool_error(
            "CONFIRMATION_REQUIRED",
            f"生成 {ticker} 报告会消耗较多模型和检索资源。请明确回复：确认生成 {ticker} 报告。",
            retryable=False,
        )

    db = SessionLocal()
    try:
        return _generate_tracking_report_impl(db, user_id, ticker)
    finally:
        db.close()


@tool
def search_my_documents(query: str, ticker: str = "", config: RunnableConfig = None) -> str:
    """在用户私有文档库中检索相关内容（不生成报告，纯检索预览）。

    【触发场景】：用户想查找自己上传的文档中关于某个话题的内容。
    【参数】：query 为检索关键词，ticker 可选标的过滤。
    """
    from uuid import UUID


    try:
        user_id_str = _get_authenticated_user_id(config)
        user_id = UUID(user_id_str)
    except (ValueError, AttributeError):
        return "文档检索暂时不可用：用户身份无效。"

    return _search_my_documents_impl(user_id, query, ticker)

@tool
def search_public_signals(query: str, source_type: str = "analysis", blogger: str = "", config: RunnableConfig = None) -> str:
    """在公共信号向量库中检索推文或分析结果（语义检索）。

    【触发场景】：用户想了解某个标的（如 LITE）的推文分析结果、市场情绪、博主观点，
    或者想查找与某话题相关的推文/分析，但不确定具体数据库查询语句。
    【参数】：
      - query: 检索关键词或问题描述，建议包含标的代码如 "LITE 分析结果"
      - source_type: 信号类型，可选 "analysis"（LLM 分析结果）或 "tweet"（原始推文），默认 "analysis"
      - blogger: 可选博主 handle（如 "qinbafrank"），限定只查该博主的信号
    【注意】：
      - search_my_documents 查的是用户上传的私有文档
      - query_database 查的是结构化 SQL 数据库（analysis_results / tweets 表）
      - 此工具查的是向量语义库 public_signals，适合找"意思相近"的内容
    """
    return _search_public_signals_impl(query, source_type, blogger)

@tool
def list_my_tracked_tickers(config: RunnableConfig = None) -> str:
    """查看当前用户订阅的所有标的跟踪列表。

    【触发场景】：用户问"我订阅了哪些""我的跟踪列表""关注了什么标的"。
    """
    from uuid import UUID

    user_id_value = ((config or {}).get("metadata") or {}).get("user_id")
    try:
        user_id = UUID(user_id_value)
    except (TypeError, ValueError, AttributeError):
        return "用户身份无效，无法查询订阅。"

    db = SessionLocal()
    try:
        return _list_my_tracked_tickers_impl(db, user_id)
    finally:
        db.close()


@tool
def list_my_followed_bloggers(config: RunnableConfig = None) -> str:
    """查看当前用户正式关注的博主列表。

    【触发场景】：用户问"我关注了哪些博主""我的关注列表""我跟踪了哪些KOL/博主"。
    【数据来源】：查询 user_blogger_follows 正式关注关系，不使用记忆偏好 watched_bloggers。
    """
    from uuid import UUID


    user_id_value = ((config or {}).get("metadata") or {}).get("user_id")
    try:
        user_id = UUID(user_id_value)
    except (TypeError, ValueError, AttributeError):
        return "用户身份无效，无法查询正式关注列表。"

    db = SessionLocal()
    try:
        return _list_my_followed_bloggers_impl(db, user_id)
    finally:
        db.close()


# Durable overrides for personal SaaS analysis confirmation.
@tool(args_schema=PreviewAnalysisArgs)
def preview_tweet_analysis(
    blogger_handle: str = "",
    reanalyze: bool = False,
    since: str = "",
    config: RunnableConfig = None,
) -> str:


    try:
        user_id = UUID(_get_authenticated_user_id(config))
    except (TypeError, ValueError, AttributeError):
        return "用户身份无效，无法创建持久化分析确认。"
    if not settings.user_analysis_requests_enabled:
        return "用户分析任务功能暂未开启。"
    if reanalyze or since:
        return "持久化分析确认暂不支持 reanalyze/since，请先使用默认 pending 推文分析。"

    handle = blogger_handle.strip().lstrip("@").lower() if blogger_handle else ""
    if handle and handle not in ("all", "全部", "所有") and not _HANDLE_RE.match(handle):
        return f"参数错误：blogger_handle '{blogger_handle}' 不是有效 Twitter Handle。"

    db = SessionLocal()
    try:
        return _preview_tweet_analysis_impl(
            db,
            user_id=user_id,
            blogger_handle=blogger_handle,
            reanalyze=reanalyze,
            since=since,
            pipeline_version=settings.user_analysis_pipeline_version,
        )
    finally:
        db.close()


@tool(args_schema=ConfirmTaskArgs)
def confirm_tweet_analysis(task_id: str, config: RunnableConfig = None) -> str:

    try:
        user_id = UUID(_get_authenticated_user_id(config))
    except (TypeError, ValueError, AttributeError):
        return "用户身份无效，无法提交分析任务。"
    if not settings.user_analysis_requests_enabled:
        return "用户分析任务功能暂未开启。"

    task_id = task_id.strip()
    try:
        confirmation_id = UUID(task_id)
    except ValueError:
        return f"确认ID '{task_id}' 无效。请重新预览。"

    db = SessionLocal()
    try:
        return _confirm_tweet_analysis_impl(
            db,
            user_id=user_id,
            confirmation_id=confirmation_id,
            daily_limit=settings.user_analysis_daily_limit,
        )
    finally:
        db.close()


tools = [
    fetch_and_save_profile, fetch_and_save_tweets,
    preview_tweet_analysis, confirm_tweet_analysis,
    query_database, search_public_signals,
    generate_tracking_report, search_my_documents, list_my_tracked_tickers,
    list_my_followed_bloggers,
]
_TOOLS_BY_NAME = {t.name: t for t in tools}
_READ_ONLY_TOOL_NAMES = [
    "query_database",
    "search_public_signals",
    "search_my_documents",
    "list_my_tracked_tickers",
    "list_my_followed_bloggers",
]
_INGEST_TOOL_NAMES = _READ_ONLY_TOOL_NAMES + [
    "fetch_and_save_profile",
    "fetch_and_save_tweets",
]
_ANALYSIS_TOOL_NAMES = _READ_ONLY_TOOL_NAMES + [
    "preview_tweet_analysis",
    "confirm_tweet_analysis",
]
_REPORT_TOOL_NAMES = _READ_ONLY_TOOL_NAMES + [
    "generate_tracking_report",
]
_tool_node = ToolNode(tools, handle_tool_errors=True)


def _latest_human_text(state: AgentState) -> str:
    messages = state.get("messages") or []
    return next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage) and isinstance(m.content, str)),
        "",
    )


def _classify_tool_route(text: str) -> tuple[str, list[str]]:
    normalized = text.lower()
    if any(k in normalized for k in ("报告", "周报", "跟踪报告", "生成报告", "report")):
        return "report", _REPORT_TOOL_NAMES
    if any(k in normalized for k in ("待分析", "预览分析", "确认分析", "分析任务", "执行分析", "confirm analysis", "preview analysis")):
        return "analysis", _ANALYSIS_TOOL_NAMES
    if any(k in normalized for k in ("抓取", "采集", "获取最新", "拉取", "同步推文", "fetch", "crawl", "最新推文")):
        return "ingest", _INGEST_TOOL_NAMES
    return "read_only", _READ_ONLY_TOOL_NAMES


_latest_human_text = _base_latest_human_text
_classify_tool_route = _base_classify_tool_route


def route_tools_node(state: AgentState, config: RunnableConfig) -> dict:
    """Classify the current user intent and expose only the needed tool subset."""
    route, allowed = _classify_tool_route(_latest_human_text(state))
    logger.info("[ChatRouter] route={} tools={}", route, allowed)
    return {"tool_route": route, "allowed_tool_names": allowed}

def tools_node(state: AgentState):
    """包装 ToolNode，追踪结构化工具调用结果中的失败状态。"""
    result = _tool_node.invoke(state)
    consecutive = state.get("consecutive_tool_failures", 0)

    messages = result.get("messages", [])
    standardized_messages = []
    has_error = False
    for msg in messages:
        if not (hasattr(msg, "content") and isinstance(msg.content, str)):
            standardized_messages.append(msg)
            continue

        content = msg.content
        envelope = _parse_tool_envelope(content)
        tool_node_status = getattr(msg, "status", None)
        if envelope is None:
            if tool_node_status == "error" or content.startswith("Error:"):
                content = _tool_error("TOOL_EXECUTION_ERROR", content, retryable=True)
            else:
                content = _tool_ok(content)
            if hasattr(msg, "model_copy"):
                msg = msg.model_copy(update={"content": content})
            else:
                msg.content = content
            envelope = _parse_tool_envelope(content)

        if envelope is not None and envelope.get("ok") is False:
            has_error = True
            logger.warning("[ToolNode] Tool failure detected: {}", content[:100])
        standardized_messages.append(msg)

    result["messages"] = standardized_messages

    if has_error:
        consecutive += 1
    else:
        consecutive = 0

    result["consecutive_tool_failures"] = consecutive
    return result


# ============================================================
# System Prompt —— 从 Prompt Registry 加载
# ------------------------------------------------------------
# 基础 prompt 从 YAML 注册表加载，运行时由 get_prompt("chat/system") 获取；
# _get_personalized_prompt() 在运行时追加用户档案与偏好，
# 实现"千人千面"：不同用户看到不同的关注博主/标的提示。
# ============================================================


def _build_prompt_from_state(base_prompt: str, profile: dict, prefs: dict, memories: list | None = None) -> str:
    sections = [base_prompt]

    profile_lines = []
    if profile.get("name"):
        profile_lines.append(f"姓名: {profile['name']}")
    if profile.get("nickname"):
        profile_lines.append(f"昵称: {profile['nickname']}")
    if profile.get("occupation"):
        profile_lines.append(f"职业: {profile['occupation']}")
    if profile.get("location"):
        profile_lines.append(f"所在地: {profile['location']}")
    if profile.get("birthday"):
        profile_lines.append(f"生日: {profile['birthday']}")
    if profile_lines:
        sections.append("用户档案：\n" + "\n".join(profile_lines))

    pref_lines = []
    if prefs.get("investment_style"):
        pref_lines.append(f"投资偏好: {prefs['investment_style']}")
    if prefs.get("watched_bloggers"):
        pref_lines.append(f"关注博主: {', '.join(prefs['watched_bloggers'])}")
    if prefs.get("interested_tickers"):
        pref_lines.append(f"关注标的: {', '.join(prefs['interested_tickers'])}")
    if prefs.get("reply_style"):
        style_label = "简洁" if prefs["reply_style"] == "concise" else "详细"
        pref_lines.append(f"回复风格: {style_label}")
    if pref_lines:
        sections.append("用户偏好：\n" + "\n".join(pref_lines))

    if memories:
        sections.append(
            "<memories>\n以下是用户的历史偏好和记忆，请结合这些信息回答：\n"
            + "\n".join(f"- {m}" for m in memories)
            + "\n</memories>"
        )

    return "\n\n".join(sections)


# ============================================================
# 上下文初始化节点 —— 图入口加载用户画像
# ------------------------------------------------------------
# 仅在每次对话开始时执行一次，将 profile/prefs 写入 State，
# 后续 agent_node 多次循环复用，避免 N+1 DB 查询。
# ============================================================

def init_context_node(state: AgentState, config: RunnableConfig) -> dict:
    return _init_context_node_impl(state, config)


# ============================================================
# Agent 核心节点 —— Token 预算 + 个性化 Prompt + LLM 调用
# ------------------------------------------------------------
# 每轮执行流程：
#   1. 估算当前消息 token 数
#   2. 超预算时安全裁剪（保留 system，从 human 起始，不破坏 tool_call 配对）
#   3. 从 State 读取已加载的 profile/prefs 注入 prompt
#   4. 调用绑定了工具的 LLM
#   5. 返回 AI 响应（可能包含 tool_calls）
# ============================================================

def agent_node(state: AgentState, config: RunnableConfig):
    messages = state["messages"]
    consecutive_failures = state.get("consecutive_tool_failures", 0)

    # 死循环防御：连续 3 次工具调用失败/报错，强制中断并返回友好提示
    if consecutive_failures >= 3:
        logger.warning("[Agent] Consecutive tool failures detected ({}). Forcing fallback response.", consecutive_failures)
        from langchain_core.messages import AIMessage
        fallback_msg = AIMessage(content="抱歉，系统当前处理您的请求时遇到连续错误，请稍后再试或换一种方式提问。")
        return {"messages": [fallback_msg], "consecutive_tool_failures": 0}

    # Build system prompt first to account for its token cost in the budget
    profile = state.get("user_profile") or {}
    prefs = state.get("user_prefs") or {}
    memories = state.get("memories") or []
    system_prompt = _build_prompt_from_state(get_prompt("chat/system"), profile, prefs, memories=memories)

    # System prompt tokens must be reserved from the total budget
    system_tokens = _estimate_tokens([SystemMessage(content=system_prompt)])
    available_budget = settings.agent_max_tokens_per_turn - system_tokens

    # If system prompt alone exceeds budget, reduce memories and rebuild
    if available_budget < 0 and memories:
        memories = memories[:2]
        system_prompt = _build_prompt_from_state(get_prompt("chat/system"), profile, prefs, memories=memories)
        system_tokens = _estimate_tokens([SystemMessage(content=system_prompt)])
        available_budget = settings.agent_max_tokens_per_turn - system_tokens

    # Token budget: trim safely (preserve system, start on human, keep tool_call pairs intact)
    token_estimate = _estimate_tokens(messages)
    if token_estimate > available_budget:
        logger.warning(
            "[Agent] Token budget exceeded ({} > {}), trimming messages",
            token_estimate, available_budget,
        )
        messages = trim_messages(
            messages,
            max_tokens=available_budget,
            token_counter=_estimate_tokens,
            strategy="last",
            include_system=True,
            start_on="human",
            allow_partial=False,
        )

    allowed_tool_names = state.get("allowed_tool_names") or _READ_ONLY_TOOL_NAMES
    selected_tools = [
        _TOOLS_BY_NAME[name]
        for name in allowed_tool_names
        if name in _TOOLS_BY_NAME
    ]
    llm = get_report_llm()
    llm_with_tools = llm.bind_tools(selected_tools)

    response = llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + messages
    )
    return {"messages": [response]}


# ============================================================
# mem0 记忆召回节点 —— 同步，在 Agent 回复前执行
# ------------------------------------------------------------
# 从 mem0 检索与本轮 human message 相关的跨会话历史记忆，
# 注入 AgentState.memories，供 agent_node 拼入 system prompt。
# mem0 不可用或超时时静默降级返回空列表，不阻断主链路。
# ============================================================

def mem0_recall_node(state: AgentState, config: RunnableConfig) -> dict:
    return _mem0_recall_node_impl(
        state,
        config,
        get_client=get_mem0_client,
        settings_obj=settings,
        spacy_checker=_is_mem0_spacy_model_available,
    )


# ============================================================
# mem0 记忆存储节点 —— 异步后台线程，不阻塞 SSE 响应
# ------------------------------------------------------------
# 在 extract_preferences_node 之后执行，提取本轮最后一条
# human + AI 消息，异步写入 mem0。失败静默忽略。
# ============================================================

def mem0_store_node(state: AgentState, config: RunnableConfig) -> dict:
    return _mem0_store_node_impl(state, config, get_client=get_mem0_client)


# ============================================================
# 偏好提取节点 —— 非阻塞后处理
# ------------------------------------------------------------
# Agent 回复完成后，异步解析用户最近一条消息中的隐式偏好
# （如"关注 @xxx"、"看好 BTC"），更新 DB 中的 user_preference。
# 不影响主链路延迟，失败静默忽略。
# ============================================================

def extract_preferences_node(state: AgentState, config: RunnableConfig):
    return _extract_preferences_node_impl(state, config)


# ============================================================
# 条件路由 —— 判断 Agent 是否要调用工具
# ------------------------------------------------------------
# 有 tool_calls → 进入 tools 节点执行
# 无 tool_calls → 进入 extract_preferences 完成本轮对话
# ============================================================

def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "extract_preferences"


# ============================================================
# 图构建 + 单例管理
# ------------------------------------------------------------
# 图拓扑：init → agent ←→ tools (循环) → extract_preferences → END
# init 节点仅执行一次，加载用户画像供后续节点复用，避免 N+1 查询。
# ============================================================

def build_chat_agent(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("init", init_context_node)
    graph.add_node("mem0_recall", mem0_recall_node)
    graph.add_node("route_tools", route_tools_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("extract_preferences", extract_preferences_node)
    graph.add_node("mem0_store", mem0_store_node)

    graph.add_edge(START, "init")
    graph.add_edge("init", "mem0_recall")
    graph.add_edge("mem0_recall", "route_tools")
    graph.add_edge("route_tools", "agent")
    graph.add_conditional_edges(
        "agent", should_continue, ["tools", "extract_preferences"]
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("extract_preferences", "mem0_store")
    graph.add_edge("mem0_store", END)

    return graph.compile(checkpointer=checkpointer)


_chat_agent = None


def get_chat_agent():
    global _chat_agent
    if _chat_agent is None:
        try:
            from app.memory.checkpointer import get_checkpointer
            _chat_agent = build_chat_agent(checkpointer=get_checkpointer())
        except RuntimeError:
            _chat_agent = build_chat_agent()
    return _chat_agent

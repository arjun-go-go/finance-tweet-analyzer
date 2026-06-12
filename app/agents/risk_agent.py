"""风险 Agent —— 推文风险因子识别与等级评估。

核心职责：
    对一批推文并行调用 LLM，提取结构化风险因子并评估整体风险等级。

与 analysis_agent 的分工：
    - analysis_agent：提取投资标的、情绪、观点（进攻端）
    - risk_agent：识别风险因子、评估风险等级（防御端）

二者在 Supervisor 中并行执行（Send fan-out），结果在 merge 节点合并：
risk_factors 覆盖到对应的分析记录上，形成完整的投资信号。

设计特点：
    - 6大类风险分类体系（市场/流动性/监管/技术面/事件驱动/信用违约）
    - 4档风险等级量化标准（critical/high/medium/low）
    - RiskFactor 结构化模型：category + severity + urgency + related_tickers
    - 风险黑话/暗语识别 + 反讽过滤
    - CoT reasoning 支持风控审计追溯
    - field_validator 容错 LLM 输出异常
    - asyncio.gather 批量并发，失败容忍
"""
import asyncio
import time
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.agents.llm import get_signal_llm
from app.services.blogger_context import fetch_blogger_contexts, build_blogger_context_block


# ============================================================
# 风险评估 Prompt —— 企业级量化风控
# ------------------------------------------------------------
# 6大类风险分类 + 4档量化标准 + 黑话映射 + 反讽过滤 + CoT
# ============================================================
RISK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位精通系统性风险、事件性风险、流动性风险与监管政策风险的量化风控分析师。你擅长从社交媒体短文本中精准识别风险信号，区分真实风险预警与反讽/标题党，并给出结构化风险评估。请以 json 格式输出结果。

### 风险分类体系（6大类）

**1. 市场风险 (market)**
- 价格剧烈波动、趋势反转信号、技术面破位、量价背离
- 关键词: 暴跌/崩盘/腰斩/回调/破位/跳水/闪崩

**2. 流动性风险 (liquidity)**
- 成交量萎缩、买卖价差扩大、流动性陷阱、资金出逃
- 关键词: 插针/没人接盘/流动性枯竭/深度不够/砸盘

**3. 监管政策风险 (regulatory)**
- 政策收紧、禁令、罚款、牌照吊销、合规变化
- 关键词: 监管/叫停/罚款/清退/封禁/整改/约谈

**4. 技术面风险 (technical)**
- 系统故障、智能合约漏洞、网络攻击、协议升级失败
- 关键词: 被黑/漏洞/宕机/分叉失败/MEV攻击

**5. 事件驱动风险 (event)**
- 黑天鹅事件、地缘冲突、自然灾害、重大人事变动
- 关键词: 黑天鹅/战争/制裁/暴雷/跑路/失联

**6. 信用违约风险 (credit)**
- 项目方违约、资金链断裂、庞氏暴雷、信用降级
- 关键词: 暴雷/跑路/资不抵债/挤兑/清算/归零

### 风险黑话映射
- 暴雷/爆雷 → 信用违约
- 腰斩 → 跌幅50%+，市场风险
- 矿难 → 算力暴跌/矿工抛售
- 黑天鹅 → 极端不可预测事件
- 插针 → 流动性陷阱，瞬间价格异动
- 归零 → 项目彻底失败
- 跑路 → 项目方携款潜逃
- 接飞刀 → 下跌中抄底，高亏损风险
- 埋人 → 诱多后暴跌，庄家出货

### 反讽与标题党过滤
- "要完了"可能是反讽调侃而非真实风险预警 → 结合上下文语气判断
- "核弹级利空"可能是标题党 → 看是否有具体事实支撑
- 纯情绪宣泄（"完蛋了""药丸"）若无具体风险因素 → 降级为 low

### 风险等级量化标准

**critical（紧急）**：已发生重大事件，需立即行动
- 交易所暴雷/跑路、监管明令禁止、智能合约被盗、项目清算中

**high（高风险）**：高概率近期影响投资本金
- 明确政策收紧信号、大额资金异常流出、技术面关键支撑破位

**medium（中等风险）**：存在不确定性，需密切关注
- 市场波动加剧、传闻级消息、尚未证实的负面信号

**low（低风险）**：无明显风险或纯情绪化表达
- 无具体风险因素、仅为市场正常波动讨论

### 博主背景
{blogger_context}
（要求：高信誉博主发出风险预警 → risk_level 权重提升，更可能是真实风险信号；标题党/营销号/新博主 → 谨慎判断，倾向降级为 medium 或 low。）

### 分类提示
{classification_hint}

### reasoning（思维链）
简要写出：1.识别了哪些风险信号/黑话 2.风险分类依据 3.时间紧迫性判断 4.是否反讽/标题党 5.博主信誉如何影响判定 6.最终等级判定

### 输出格式

严格按以下 JSON 结构输出（risk_factors 必须为对象数组，非字符串数组）：
```json
{{
  "reasoning": "风险分析思维链...",
  "risk_factors": [
    {{
      "category": "market|liquidity|regulatory|technical|event|credit",
      "description": "风险描述（中文）",
      "severity": "critical|high|medium|low",
      "urgency": "imminent|near_term|long_term",
      "related_tickers": ["BTC", "ETH"]
    }}
  ],
  "risk_level": "critical|high|medium|low",
  "risk_summary": "一句话风险概述"
}}
```
注意：risk_factors 不是字符串数组，是对象数组。每个对象必须包含 category/description/severity/urgency/related_tickers 五个字段。无风险时 risk_factors 为空数组 []，risk_level 为 "low"。"""),
    ("human", "博主: @{author_handle}\n推文内容: {content}")
])


# ============================================================
# 结构化输出 Schema —— 风险因子细粒度模型
# ============================================================
class RiskFactor(BaseModel):
    """单个风险因子的结构化描述。"""
    category: Literal["market", "liquidity", "regulatory", "technical", "event", "credit"] = Field(
        description="风险分类: market/liquidity/regulatory/technical/event/credit"
    )
    description: str = Field(description="风险描述（中文简述）")
    severity: Literal["critical", "high", "medium", "low"] = Field(
        default="medium", description="该因子严重程度"
    )
    urgency: Literal["imminent", "near_term", "long_term"] = Field(
        default="near_term",
        description="时间紧迫性: imminent(已发生/即将), near_term(数天~数周), long_term(潜在长期)"
    )
    related_tickers: list[str] = Field(
        default_factory=list, description="该风险影响的标的代码列表"
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v):
        if not isinstance(v, str):
            return "market"
        mapping = {
            "市场": "market", "流动性": "liquidity", "监管": "regulatory",
            "技术": "technical", "事件": "event", "信用": "credit",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "market"

    @field_validator("related_tickers", mode="before")
    @classmethod
    def _ensure_ticker_list(cls, v):
        if not isinstance(v, list):
            return []
        return [str(x).strip().upper() for x in v if x]


class TweetRiskAssessment(BaseModel):
    """单条推文的风险评估结果。

    生产级 Schema：
        - RiskFactor 结构化风险因子（分类 + 严重度 + 紧迫性 + 关联标的）
        - 4档风险等级 (critical/high/medium/low)
        - CoT reasoning 支持审计追溯
        - field_validator 容错 LLM 异常输出
        - @property 保持向后兼容
    """
    reasoning: str = Field(
        default="",
        description="分析逻辑链：1.风险信号识别 2.分类 3.紧迫性 4.反讽判断 5.等级判定"
    )
    risk_factors: list[RiskFactor] = Field(
        default_factory=list, description="结构化风险因子列表"
    )
    risk_level: Literal["critical", "high", "medium", "low"] = Field(
        default="low", description="综合风险等级（取所有因子中最高 severity）"
    )
    risk_summary: str = Field(
        default="", description="一句话风险概述"
    )

    # ----------------------------------------------------------
    # LLM 输出容错 validators
    # ----------------------------------------------------------
    @field_validator("risk_factors", mode="before")
    @classmethod
    def _ensure_risk_list(cls, v):
        """兼容 LLM 偶尔返回 null 或非数组。"""
        return v if isinstance(v, list) else []

    @field_validator("risk_level", mode="before")
    @classmethod
    def _normalize_risk_level(cls, v):
        """容错：LLM 可能返回中文或非标准值。"""
        if not isinstance(v, str):
            return "low"
        mapping = {
            "紧急": "critical", "严重": "critical", "极高": "critical",
            "高": "high", "高风险": "high",
            "中": "medium", "中等": "medium", "中风险": "medium",
            "低": "low", "低风险": "low", "无": "low",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "low"

    @field_validator("risk_summary", mode="before")
    @classmethod
    def _ensure_str(cls, v):
        """确保 risk_summary 为字符串。"""
        if v is None:
            return ""
        return str(v)

    # ----------------------------------------------------------
    # 向后兼容属性 —— 供 merge 节点消费旧格式
    # ----------------------------------------------------------
    @property
    def risk_factor_texts(self) -> list[str]:
        """返回纯文本风险因素列表，兼容旧版 risk_assessments[*]['risk_factors'] 为 list[str] 的消费方。"""
        return [f.description for f in self.risk_factors]


# ============================================================
# 单条推文风险评估 —— 异步 LLM 调用
# ============================================================
async def _assess_one(chain, tweet: dict, blogger_context: str, classification_hint: str) -> dict | None:
    """对单条推文执行风险评估，返回结构化结果或 None（失败时）。"""
    start = time.perf_counter()
    try:
        result = await chain.ainvoke({
            "content": tweet["content"],
            "author_handle": tweet["author_handle"],
            "blogger_context": blogger_context,
            "classification_hint": classification_hint,
        })
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = result.model_dump()
        data["tweet_id"] = tweet["id"]
        data["_latency_ms"] = latency_ms
        logger.debug(
            "[Risk] tweet={} latency={}ms risk_level={}",
            tweet["id"][:8], latency_ms, data.get("risk_level", "low"),
        )
        return data
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.warning("Risk agent failed for tweet {} ({}ms): {}", tweet["id"], latency_ms, e)
        return None


# ============================================================
# 批量风险评估编排
# ------------------------------------------------------------
# 对所有输入推文并行调用 LLM（不做过滤，因为 Supervisor 路由
# 时已确保只有 needs_risk_analysis=true 的推文才发送到这里）。
# ============================================================
async def _run_risk(state: dict) -> dict:
    """批量执行风险评估，注入博主画像和分类提示，asyncio.gather 并发。"""
    tweets = state["tweets"]
    classifications = state.get("classifications", [])

    # #14: 批量获取博主历史画像（共享 service，与 analysis_agent 解耦）
    handles = list({t["author_handle"] for t in tweets})
    blogger_contexts = fetch_blogger_contexts(handles)
    context_block = build_blogger_context_block(blogger_contexts)

    # #15: 构建 tweet_id -> 分类提示映射
    category_map = {c["tweet_id"]: c.get("category", "") for c in classifications}
    category_hints = {
        "risk_warning": "该推文被分类为「风险预警」，重点识别具体风险因子和紧迫性。",
        "investment": "该推文被分类为「投资建议」，关注其中隐含的风险因素。",
        "market_commentary": "该推文被分类为「市场评论」，评估是否包含潜在风险信号。",
    }

    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(TweetRiskAssessment)
    chain = RISK_PROMPT | structured_llm

    tasks = []
    for tweet in tweets:
        cat = category_map.get(tweet["id"], "")
        hint = category_hints.get(cat, "无特殊分类提示。")
        tasks.append(_assess_one(chain, tweet, context_block, hint))

    results = await asyncio.gather(*tasks)
    risk_assessments = [r for r in results if r is not None]

    if risk_assessments:
        latencies = [r.get("_latency_ms", 0) for r in risk_assessments]
        logger.info(
            "[Risk] batch done: total={} assessed={} avg_latency={}ms max_latency={}ms",
            len(tweets), len(risk_assessments),
            sum(latencies) // len(latencies), max(latencies),
        )

    return {"risk_assessments": risk_assessments}


# ============================================================
# LangGraph 节点入口 —— 事件循环兼容
# ------------------------------------------------------------
# 与 analysis_agent_node 相同的线程池桥接策略。
# ============================================================
def risk_agent_node(state: dict) -> dict:
    """风险 Agent 的 LangGraph 节点入口。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run_risk(state)).result()
    return asyncio.run(_run_risk(state))

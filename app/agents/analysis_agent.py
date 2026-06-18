"""分析 Agent —— 推文投资信号提取。

核心职责：
    对一批推文逐条调用 LLM，提取 tickers / sentiment / horizon / key_points 等结构化字段。

关键设计：
    1. 博主画像注入 (blogger_context)：查询历史可信度 + 情绪分布，写入 system prompt，
       让 LLM 参考博主过往表现给出差异化置信度 → 形成可信度反馈闭环。
    2. 非金融推文快速跳过：classify 阶段已标记 non_financial 的推文直接构造空结果，
       不走 LLM，节省 token 成本。
    3. asyncio.gather 并发：所有推文的 LLM 调用并行执行，批处理延迟等于最慢单条。
"""
import asyncio
import time

from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from app.agents.llm import get_signal_llm
from app.prompts import get_chat_prompt
from app.schemas.signal import TweetAnalysis
from app.services.blogger_context import fetch_blogger_contexts, build_blogger_context_block


# ============================================================
# 分析 Prompt —— 已迁移至 prompts/analysis.yaml
# ------------------------------------------------------------
# Prompt 模板通过 get_chat_prompt("analysis/system_prompt") 加载，
# 运行时变量 blogger_context / author_handle / content 由 Jinja2 渲染。
# ============================================================


def _to_lc_messages(msg_dicts: list[dict]) -> list:
    """将 get_chat_prompt 返回的 dict 列表转换为 LangChain Message 对象。"""
    _ROLE_MAP = {"system": SystemMessage, "human": HumanMessage}
    return [_ROLE_MAP[m["role"]](content=m["content"]) for m in msg_dicts]




# ============================================================
# 单条推文分析 —— 异步 LLM 调用
# ------------------------------------------------------------
# 调用 structured_output 模式确保返回 TweetAnalysis schema，
# 记录延迟用于性能监控。失败返回 None，不阻塞批量处理。
# ============================================================
async def _analyze_one(structured_llm, tweet: dict, blogger_context: str) -> dict | None:
    """对单条推文执行 LLM 分析，返回结构化结果或 None（失败时）。"""
    start = time.perf_counter()
    try:
        messages = _to_lc_messages(get_chat_prompt(
            "analysis/system_prompt",
            blogger_context=blogger_context,
            author_handle=tweet["author_handle"],
            content=tweet["content"],
        ))
        result = await structured_llm.ainvoke(messages)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = result.model_dump()
        data["tweet_id"] = tweet["id"]
        data["author_handle"] = tweet["author_handle"]
        data["_latency_ms"] = latency_ms
        logger.debug(
            "[Analysis] tweet={} latency={}ms confidence={}",
            tweet["id"][:8], latency_ms, data.get("confidence", 0),
        )
        return data
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.warning("Analysis agent failed for tweet {} ({}ms): {}", tweet["id"], latency_ms, e)
        return None


# ============================================================
# 批量分析编排 —— 异步入口
# ------------------------------------------------------------
# 流程：
#   1. 从 classify 结果过滤 non_financial → 直接构造空结果（跳过 LLM）
#   2. 对剩余推文批量查询博主画像 → 注入 prompt
#   3. asyncio.gather 并发执行所有 LLM 调用
#   4. 汇总返回 partial_analyses（由 operator.add 在 StateGraph 合并）
# ============================================================
async def _run_analysis(state: dict) -> dict:
    tweets = state["tweets"]
    classifications = state.get("classifications", [])

    # 标记为非金融的推文 ID 集合（无需 LLM 分析）
    non_financial_ids = {
        c["tweet_id"] for c in classifications
        if c.get("category") == "non_financial"
    }

    # 批量获取涉及博主的历史画像
    handles = list({t["author_handle"] for t in tweets})
    blogger_contexts = fetch_blogger_contexts(handles)
    context_block = build_blogger_context_block(blogger_contexts)

    # 构建 structured LLM（prompt 通过 get_chat_prompt 加载）
    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(TweetAnalysis)

    tasks = []
    skipped = []
    for tweet in tweets:
        if tweet["id"] in non_financial_ids:
            # 非金融推文：不调用 LLM，直接构造空分析结果
            skipped.append({
                "tweet_id": tweet["id"],
                "author_handle": tweet["author_handle"],
                "reasoning": "分类阶段判定为非金融内容，跳过分析",
                "is_investment_related": False,
                "overall_sentiment": "neutral",
                "tickers": [],
                "key_points": [],
                "risk_factors": [],
                "confidence": 0.0,
            })
        else:
            tasks.append(_analyze_one(structured_llm, tweet, context_block))

    # 并发执行所有 LLM 调用
    results = await asyncio.gather(*tasks)
    successful = [r for r in results if r is not None]
    partial_analyses = skipped + successful

    if successful:
        latencies = [r.get("_latency_ms", 0) for r in successful]
        logger.info(
            "[Analysis] batch done: total={} analyzed={} skipped={} avg_latency={}ms max_latency={}ms",
            len(tweets), len(successful), len(skipped),
            sum(latencies) // len(latencies), max(latencies),
        )

    return {"partial_analyses": partial_analyses}


# ============================================================
# LangGraph 节点入口
# ------------------------------------------------------------
# LangGraph 的 ToolNode / Send 可能在已有事件循环中调用本节点，
# 此时 asyncio.run() 会抛 RuntimeError。
# 解决方案：检测到已有运行循环时，用线程池桥接异步执行。
# ============================================================
def analysis_agent_node(state: dict) -> dict:
    """分析 Agent 的 LangGraph 节点入口，处理事件循环兼容性。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 已有事件循环（如 FastAPI 的 async 上下文）→ 线程池桥接
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run_analysis(state)).result()
    return asyncio.run(_run_analysis(state))

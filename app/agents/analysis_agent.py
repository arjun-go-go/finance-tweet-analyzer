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

from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from app.agents.llm import get_signal_llm
from app.schemas.signal import TweetAnalysis
from app.services.blogger_context import fetch_blogger_contexts, build_blogger_context_block


# ============================================================
# 分析 Prompt —— system 模板
# ------------------------------------------------------------
# {blogger_context} 占位符在运行时被替换为博主历史画像信息，
# 使 LLM 能参考博主历史命中率/情绪偏好来调整 confidence 输出。
# ============================================================
ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位顶级量化金融情绪分析师，精通全球股票、加密货币、外汇及大宗商品市场。你擅长从社交媒体短文本中精准提取投资标的、识别金融黑话与反讽，并给出校准的置信度。请以 json 格式输出结构化分析结果。

### 博主背景
{blogger_context}
（要求：结合博主历史胜率和信誉度动态调整 confidence。高胜率 KOL 的明确逻辑 → 提升置信度；经常反指/情绪化/新博主 → 降低置信度。）

### 分析规则

**1. 标的识别与标准化 (tickers)**
- 提取所有投资标的，进行代码标准化映射：
  大饼/比特币→BTC, 以太/姨太→ETH, 纳指→NDX, 标普→SPX,
  黄金→XAUUSD, 原油→CL, 特斯拉/马斯克概念→TSLA, 茅台→600519.SH
- 多标的时为每个标的独立评估 sentiment 和 horizon

**2. 情绪判定 (sentiment)**
- bullish: 看多/买入/加仓/抄底
- bearish: 看空/卖出/做空/减仓/割肉
- neutral: 中性/观望/仅陈述事实
- 防反讽与黑话：
  "钻石手/Diamond hands"=bullish, "纸手"=bearish, "接飞刀"=bearish,
  "to the moon"=bullish, "归零"=bearish
  反讽（如"跌得真漂亮"）需结合上下文和博主历史判断真实意图

**3. 投资周期 (horizon)**
- short: 日内~几天, medium: 几周~几月, long: 半年以上, unknown: 未提及

**4. 核心观点 (key_points)**
- 提炼 1-3 条投资逻辑或催化剂（财报/技术面/宏观/政策等）
- 纯情绪宣泄无实质逻辑 → 留空

**5. 置信度校准 (confidence)**
- >0.8: 标的明确 + 逻辑清晰 + 博主高信誉
- 0.5~0.8: 存在模糊性/黑话/博主信誉一般
- 0.3~0.5: 标的不够明确或逻辑薄弱
- <0.3: 纯闲聊/严重反讽/知名反指博主/非投资内容

**6. reasoning (思维链)**
- 简要写出：1.识别了哪些标的及黑话 2.真实情绪判断依据 3.博主背景如何影响置信度

### 输出格式

严格按以下 JSON 结构输出（tickers 必须为对象数组，每个标的独立 sentiment 和 horizon）：
```json
{{
  "reasoning": "思维链分析过程...",
  "is_investment_related": true,
  "overall_sentiment": "bullish|bearish|neutral|mixed",
  "tickers": [
    {{
      "symbol": "BTC",
      "original_name": "大饼",
      "sentiment": "bullish|bearish|neutral",
      "horizon": "short|medium|long|unknown"
    }}
  ],
  "key_points": ["观点1", "观点2"],
  "risk_factors": ["风险1"],
  "confidence": 0.75
}}
```
注意：tickers 不是字符串数组，是对象数组。每个对象必须包含 symbol/original_name/sentiment/horizon 四个字段。"""),
    ("human", "博主: @{author_handle}\n推文内容: {content}")
])




# ============================================================
# 单条推文分析 —— 异步 LLM 调用
# ------------------------------------------------------------
# 调用 structured_output 模式确保返回 TweetAnalysis schema，
# 记录延迟用于性能监控。失败返回 None，不阻塞批量处理。
# ============================================================
async def _analyze_one(chain, tweet: dict, blogger_context: str) -> dict | None:
    """对单条推文执行 LLM 分析，返回结构化结果或 None（失败时）。"""
    start = time.perf_counter()
    try:
        result = await chain.ainvoke({
            "content": tweet["content"],
            "author_handle": tweet["author_handle"],
            "blogger_context": blogger_context,
        })
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

    # 构建 LLM chain：ANALYSIS_PROMPT → structured TweetAnalysis
    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(TweetAnalysis)
    chain = ANALYSIS_PROMPT | structured_llm

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
            tasks.append(_analyze_one(chain, tweet, context_block))

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

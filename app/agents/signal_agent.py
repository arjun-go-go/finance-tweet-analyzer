"""信号 Agent —— 单条推文独立分析（早期版本/工具调用入口）。

与 analysis_agent 的区别：
    - signal_agent: 同步、单条调用，无 blogger_context 注入，用于 chat_agent 工具链
    - analysis_agent: 异步批量并发，注入博主画像上下文，用于 Supervisor 管道

本模块作为独立入口保留，供不经过 Supervisor 的场景使用
（如手动调试、单条推文快速分析等）。
"""
from langchain_core.prompts import ChatPromptTemplate

from app.agents.llm import get_signal_llm
from app.schemas.signal import TweetAnalysis

# ============================================================
# 推文分析 Prompt（单条版本，无 blogger_context）
# ============================================================
TWEET_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的金融投资分析师。你的任务是分析金融博主的推文，判断其中是否包含投资建议，并提取关键信息。

分析规则：
1. tickers: 识别推文中提到的所有投资标的（股票代码、加密货币、ETF、商品等）。注意识别中文名称（如"贵州茅台"→"贵州茅台"，"比特币"→"BTC"）
2. sentiment: 判断博主对提到的标的整体态度——bullish(看好买入)、bearish(看空卖出)、neutral(中性观望)
3. investment_horizon: 判断投资周期——short(短期/几天到几周)、medium(中期/几周到几月)、long(长期/半年以上)
4. key_points: 提取推文中的核心投资观点，每条简明扼要
5. risk_factors: 博主提到的风险或不确定因素
6. confidence: 你对分析结果的置信度(0-1)。日常闲聊、非投资内容应低于0.2
7. is_investment_related: 该推文是否真正包含投资相关内容（闲聊/生活分享等填false）

重点关注：博主对标的的推荐态度、看好理由、风险提示。不要过度解读非投资内容。

请以 JSON 格式输出分析结果。"""),
    ("human", "博主: {author_handle}\n推文内容: {content}")
])


def analyze_tweet(content: str, author_handle: str) -> dict:
    """同步分析单条推文，返回结构化字典。

    适用场景：chat_agent 工具调用 / 手动调试 / 实时单条分析。
    不注入 blogger_context（无批量上下文优化）。
    """
    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(TweetAnalysis)
    chain = TWEET_ANALYSIS_PROMPT | structured_llm
    result = chain.invoke({"content": content, "author_handle": author_handle})
    return result.model_dump()

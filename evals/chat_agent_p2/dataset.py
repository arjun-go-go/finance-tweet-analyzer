"""Frozen business-case generators for Chat Agent P2 evaluation."""
from __future__ import annotations

from itertools import product


ENTITIES = ("TSLA", "BTC", "AAPL", "NVDA", "ETH", "MSFT")
BLOGGERS = ("elonmusk", "qinbafrank", "unusual_whales", "zerohedge", "saylor", "CathieDWood")
CONFIRMATION_ID = "6bbfd1be-f528-4c8a-a221-94a4b3a75933"


def _cross(category: str, expected_tool: str | None, templates: tuple[str, ...], values: tuple[str, ...]) -> list[dict]:
    return [
        {
            "id": f"{category}-{template_index}-{value_index}",
            "category": category,
            "input": template.format(value=value),
            "expected_tool": expected_tool,
        }
        for (template_index, template), (value_index, value) in product(
            enumerate(templates), enumerate(values)
        )
    ]


def selection_cases() -> list[dict]:
    cases = []
    cases += _cross(
        "database",
        "query_database",
        (
            "查询数据库里 {value} 的历史分析结果",
            "{value} 最近有哪些已经入库的预测？",
            "数据库中提到 {value} 的推文有多少条？",
            "历史数据里对 {value} 看多的博主是谁？",
            "给我看 {value} 已保存的情绪统计",
        ),
        ENTITIES,
    )
    cases += _cross(
        "public_signals",
        "search_public_signals",
        (
            "市场博主怎么看 {value}？",
            "检索关于 {value} 的分析观点",
            "{value} 最近的市场情绪如何？",
            "公共信号库里有哪些 {value} 风险提示？",
            "找出与 {value} 相关的看多和看空观点",
            "从推文分析中总结 {value} 的主要观点",
        ),
        ENTITIES,
    )
    cases += _cross(
        "private_documents",
        "search_my_documents",
        (
            "我上传的研报如何评价 {value}？",
            "在我的文档里检索 {value}",
            "我的 PDF 对 {value} 的目标价是多少？",
            "根据我上传的材料总结 {value} 风险",
            "私人知识库中有没有提到 {value}？",
        ),
        ENTITIES,
    )
    cases += _cross(
        "fetch_profile",
        "fetch_and_save_profile",
        (
            "获取 @{value} 的主页资料",
            "更新 {value} 的个人简介和粉丝数",
            "fetch profile for {value}",
            "查看 {value} 的主页信息",
            "同步博主 {value} 的最新资料",
        ),
        BLOGGERS,
    )
    cases += _cross(
        "fetch_tweets",
        "fetch_and_save_tweets",
        (
            "抓取 @{value} 的最新推文",
            "看看 {value} 最近发了什么",
            "同步 {value} 的推文",
            "fetch latest tweets from {value}",
            "采集博主 {value} 刚刚发布的内容",
        ),
        BLOGGERS,
    )
    cases += _cross(
        "report",
        "generate_tracking_report",
        (
            "生成 {value} 跟踪报告",
            "给我做一份 {value} 周报",
            "create a {value} report",
            "写一份 {value} 投资分析报告",
            "立即生成 {value} 日报",
        ),
        ENTITIES,
    )

    fixed = {
        "tracked_tickers": (
            "列出我的订阅标的", "我现在追踪哪些股票？", "查看我的 ticker 订阅",
            "我的关注标的有哪些？", "show my tracked tickers", "当前订阅列表",
            "我订阅了哪些币？", "查看个人追踪标的", "列出我的日报订阅对象",
            "哪些 ticker 在我的列表中？", "我的标的订阅状态", "查询我追踪的资产",
        ),
        "followed_bloggers": (
            "我正式关注了哪些博主？", "列出我的博主关注列表", "我关注的 KOL 有谁？",
            "show my followed bloggers", "个人工作台关注了谁？", "查询我的关注博主",
            "我的正式博主列表", "我跟踪了哪些推特账号？", "关注关系里有哪些博主？",
            "列出我的 KOL", "查看本人关注账号", "我的博主关注状态",
        ),
        "preview_analysis": (
            "预览待分析推文", "开始分析待处理推文", "创建推文分析任务", "看看有多少待分析数据",
            "preview tweet analysis", "提交分析前先预览", "分析所有 pending 推文", "准备执行推文分析",
            "列出待分析推文统计", "我要分析新采集的数据", "开始深度分析推文", "生成分析任务预览",
        ),
        "no_tool": (
            "你好", "什么是多头情绪？", "解释一下 RRF", "金融推文分析有什么价值？",
            "报告里一般有哪些章节？", "如何理解止损？", "谢谢", "你能做什么？",
            "什么是 ticker？", "介绍一下向量检索", "不要生成报告，只解释概念", "不用抓取，告诉我采集是什么",
            "什么是市场情绪？", "解释基本面和技术面的区别", "早上好", "如何写投资复盘？",
            "什么叫风险收益比？", "说明一下多 Agent 架构", "什么是 rerank？", "晚安",
        ),
    }
    expected = {
        "tracked_tickers": "list_my_tracked_tickers",
        "followed_bloggers": "list_my_followed_bloggers",
        "preview_analysis": "preview_tweet_analysis",
        "no_tool": None,
    }
    for category, messages in fixed.items():
        cases.extend(
            {
                "id": f"{category}-{index}",
                "category": category,
                "input": message,
                "expected_tool": expected[category],
            }
            for index, message in enumerate(messages)
        )

    confirmation_context = (
        f"待分析推文统计：共 18 条\n确认ID: {CONFIRMATION_ID}\n"
        "是否确认提交后台分析？"
    )
    for index, message in enumerate(("确认", "好的", "可以", "执行", "开始", "go ahead", "confirm", "确认提交", "立即执行", "是的，继续", "没问题", "提交吧")):
        cases.append({
            "id": f"confirm_analysis-{index}",
            "category": "confirm_analysis",
            "input": message,
            "history": confirmation_context,
            "expected_tool": "confirm_tweet_analysis",
        })
    return cases


def evidence_cases() -> list[dict]:
    success_facts = (
        ("list_my_followed_bloggers", "我关注了哪些博主？", "你正式关注了 @qinbafrank。", "qinbafrank"),
        ("list_my_tracked_tickers", "我订阅了哪些标的？", "你的订阅列表包含 TSLA。", "TSLA"),
        ("query_database", "数据库里有多少推文？", "数据库查询结果：共有 18 条推文。", "18"),
        ("search_public_signals", "博主怎么看 BTC？", "[1] @qinbafrank 对 BTC 持看多观点，时间 2026-08-09。", "看多"),
        ("search_my_documents", "我的研报如何评价 NVDA？", "[1] 文档认为 NVDA 的主要风险是估值过高。", "估值过高"),
    )
    cases = []
    for tool_name, question, result, fact in success_facts:
        for index in range(4):
            cases.append({
                "id": f"evidence-success-{tool_name}-{index}",
                "kind": "success",
                "tool": tool_name,
                "input": question,
                "tool_result": result,
                "required_fact": fact,
                "required_citation": f"【tool:{tool_name}】",
            })
    for index, (tool_name, question) in enumerate((
        ("search_public_signals", "BTC 现在市场情绪如何？"),
        ("search_my_documents", "我的文档给 TSLA 的目标价是多少？"),
        ("query_database", "数据库里最新预测是什么？"),
        ("list_my_followed_bloggers", "我关注了哪些博主？"),
        ("list_my_tracked_tickers", "我订阅了哪些标的？"),
    )):
        cases.append({
            "id": f"evidence-empty-{index}",
            "kind": "empty",
            "tool": tool_name,
            "input": question,
            "tool_result": "未找到相关数据。",
            "required_citation": f"【tool:{tool_name}】",
        })
        cases.append({
            "id": f"evidence-error-{index}",
            "kind": "error",
            "tool": tool_name,
            "input": question,
            "tool_error": "检索服务暂时不可用。",
            "forbidden_citation": f"【tool:{tool_name}】",
        })
    return cases

"""新切块逻辑的针对性测试：结构感知 + 短块合并 + 清洗。

跑法：
  cd finance-tweet-analyzer
  uv run pytest tests/unit/rag/test_chunking_v2.py -v

也支持直接执行查看可视化输出：
  uv run python tests/unit/rag/test_chunking_v2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许直接 `uv run test_chunking_v2.py`：把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from app.rag.chunking import (
    _clean_tweet_text,
    _merge_small_chunks,
    _pre_split_by_structure,
    chunk_tweet, chunk_document,
)


# ============================================================
# 1. 轻量清洗
# ============================================================
class TestCleanTweetText:
    def test_compress_excessive_newlines(self):
        text = "第一段\n\n\n\n\n第二段"
        assert _clean_tweet_text(text) == "第一段\n\n第二段"

    def test_keep_double_newline(self):
        text = "第一段\n\n第二段"
        assert _clean_tweet_text(text) == "第一段\n\n第二段"

    def test_strip_outer_whitespace(self):
        assert _clean_tweet_text("  hello  \n\n") == "hello"


# ============================================================
# 2. 结构感知预切分
# ============================================================
class TestPreSplitByStructure:
    def test_arabic_numbered_list(self):
        text = "总结：\n1. 看多英伟达\n2. 看空特斯拉\n3. 持有苹果"
        parts = _pre_split_by_structure(text)
        assert len(parts) == 4
        assert parts[1].startswith("1.")
        assert parts[2].startswith("2.")
        assert parts[3].startswith("3.")

    def test_chinese_numbered_list(self):
        text = "观点：\n一、宏观面\n二、技术面\n三、资金面"
        parts = _pre_split_by_structure(text)
        # 中文序号被识别为结构边界
        assert len(parts) >= 3
        assert any(p.startswith("一、") for p in parts)

    def test_dash_bullet(self):
        text = "AVGO 财报要点：\n- Revenue 100B+\n- Networking demand insatiable\n- 2027 大订单"
        parts = _pre_split_by_structure(text)
        assert len(parts) == 4
        assert parts[1].startswith("- Revenue")

    def test_paren_numbered(self):
        text = "风险因素：\n(1) 估值高\n(2) 通胀\n(3) 地缘"
        parts = _pre_split_by_structure(text)
        assert len(parts) == 4
        assert parts[1].startswith("(1)")

    def test_no_structure_returns_single(self):
        text = "这是一段没有任何列表结构的普通文字，只是一句话而已。"
        parts = _pre_split_by_structure(text)
        assert len(parts) == 1


# ============================================================
# 3. 短块合并
# ============================================================
class TestMergeSmallChunks:
    def test_merge_under_size(self):
        chunks = ["A" * 30, "B" * 30, "C" * 30]
        merged = _merge_small_chunks(chunks, chunk_size=100)
        # 三块 30 字 + 两个 \n 拼接 = 92 字 ≤ 100，应合并为一块
        assert len(merged) == 1

    def test_split_when_exceeds_size(self):
        chunks = ["A" * 60, "B" * 60, "C" * 60]
        merged = _merge_small_chunks(chunks, chunk_size=100)
        # 任意两块拼接超过 100，不能合并，保持 3 块
        assert len(merged) == 3

    def test_partial_merge(self):
        chunks = ["A" * 30, "B" * 30, "C" * 80]
        merged = _merge_small_chunks(chunks, chunk_size=100)
        # 前两块合并成 61 字，第三块单独 80 字
        assert len(merged) == 2

    def test_empty_input(self):
        assert _merge_small_chunks([], chunk_size=100) == []

    def test_single_chunk_passthrough(self):
        assert _merge_small_chunks(["only"], chunk_size=100) == ["only"]


# ============================================================
# 4. chunk_tweet 端到端
# ============================================================
class TestChunkTweetE2E:
    def test_short_tweet_no_split(self):
        text = "看多 $NVDA，AI 算力需求持续旺盛。"
        assert chunk_tweet(text) == [text]

    def test_long_structured_tweet_preserves_lists(self):
        # 用较低的阈值触发切分路径，验证结构感知 + 合并的端到端行为
        intro = "今日复盘：" + "市场延续震荡，半导体板块表现强势。" * 15
        body = "\n".join([f"{i}. 标的 #{i} 的核心逻辑：技术面突破/基本面改善/资金面流入。" for i in range(1, 8)])
        text = intro + "\n\n" + body

        chunks = chunk_tweet(text, long_tweet_threshold=200, chunk_size=200, chunk_overlap=20)
        # 至少切出多块
        assert len(chunks) > 1
        # 每块都不超长
        assert all(len(c) <= 200 for c in chunks)

    def test_no_micro_fragments_after_merge(self):
        """回归测试：合并优化后不应产生大量 < 30 字的碎片。"""
        body = "\n".join([f"{i}. ${'A' * 5} 看多原因{i}" for i in range(1, 30)])
        text = "持仓清单：\n" + body
        chunks = chunk_tweet(text)
        # 经过合并后，单块不应低于 30 字（最后一块除外）
        small_count = sum(1 for c in chunks[:-1] if len(c) < 30)
        assert small_count == 0, f"出现 {small_count} 个短碎片：{[c for c in chunks if len(c) < 30]}"

    def test_structure_preserved_at_boundaries(self):
        """结构边界保留：合并后的块仍以列表序号开头。"""
        body = "\n".join([f"{i}. " + "X" * 100 for i in range(1, 8)])
        text = "要点：\n" + body  # 每个列表项约 103 字
        chunks = chunk_tweet(text)
        # 大部分 chunk 应以列表序号或 "要点：" 开头
        starts_with_struct = sum(
            1 for c in chunks
            if c.lstrip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "要点"))
        )
        assert starts_with_struct >= len(chunks) - 1

    def test_empty_tweet(self):
        assert chunk_tweet("") == []
        assert chunk_tweet("   \n  ") == []

    def test_excessive_newlines_normalized(self):
        text = "第一部分\n\n\n\n\n" + "X" * 600 + "\n\n\n第二部分"
        chunks = chunk_tweet(text)
        # 不应因为多余换行而出现空块或异常
        assert all(c.strip() for c in chunks)


# ============================================================
# 5. 可视化运行（直接 python 执行时输出对比）
# ============================================================
def _demo():
    """直接运行脚本时打印各种典型场景的切块结果。"""
    cases = {
        "文档":"""国会山 — 美国国会参议院军事委员会推进一项重要国防授权法案。法案将中国列为对美国利益构成挑战的“侵略者轴心”(Axis of Aggressors)成员之一。法案目标在于提升第一岛链整体防御战备水平，从而加强美国对中国的威慑力。法案还授权向台湾提供安全援助、为台湾建立战时储备物资库，以及审查对台及其他地区伙伴的武器销售延误情况。该法案的众议院版本日前已在众议院委员会获得通过。 参议院军事委员会星期三(6月10日)以18票支持、9票反对的表决结果通过参院版本2027财年《国防授权法》(National Defense Authorization Act，简称NDAA)。这项总额达1.15万亿美元的国防开支计划接下来将送交参议院院会等候审议表决。 中国被列为对美国利益构成挑战的“侵略者轴心”成员之一 根据参议院军事委员会公布的法案摘要，法案将中国列为对美国利益构成挑战的“侵略者轴心”(Axis of Aggressors)成员之一。 “面对以中国、俄罗斯、伊朗和朝鲜为首的侵略者阵营，美国目前正处于二战以来最危险的威胁环境中。”摘要写道。 参议院军事委员会主席、来自密西西比州的共和党联邦参议员罗杰·威克(Roger Wicker)星期四在一份书面声明中表示，美国当前面临的威胁前所未有地复杂且紧迫。 “一个侵略者轴心正在全球范围内挑战美国的利益，而战争的性质也在迅速演变。” 威克说。 他表示，鉴于美国军队必须具备遏制这些威胁、并在必要时战胜对手的能力，2027财年《国防授权法》代表着美国军力建设的一项重大突破。 “通过前所未有规模的投资，以及在组织架构和采购机制方面的大胆改革，这项法案将加速推进美军现代化建设，并塑造下一代战争的格局。”威克说。 参议院军事委员会首席民主党议员、来自罗德岛的民主党联邦参议员杰克·里德(Jack Reed)也在声明中表示，法案获得了两党支持，他仍会持续“努力改进这项法案。” “这项跨党派支持的《国防授权法》既加强了国防建设，又强化了监督与问责机制。它要求(国防)部长对国会承担更多责任，并将防止过去的许多错误在未来重演。推动该法案的通过，是这一多步骤进程中必不可少的一步。”里德说。 第一岛链安全合作倡议和台湾战时储备库 根据法案摘要，法案将现行“台湾安全合作倡议”(Taiwan Security Cooperation Initiative)更名为“第一岛链安全合作倡议”(First Island Chain Security Cooperation Initiative，简称FICSCI)，并将菲律宾纳入援助适用对象，同时将该倡议的授权期限延长至2032年。 此举凸显华盛顿正将其印太战略布局从以台湾为重点，进一步扩展至整个第一岛链，强化与区域盟友及伙伴的安全合作，构建更具韧性的前沿防御体系，以应对中国在印太地区日益扩大的军事活动和影响力。这一方向也与五角大楼今年早些时候公布的《2026年国防战略》所强调的印太防务重点相呼应。 在台湾议题方面，法案授权五角大楼为台湾建立战时储备库(War Reserve Stockpile)计划，以提升台湾在潜在冲突中的后勤保障和持续作战能力。 与此同时，法案要求审查美国通过“对外军事销售”(Foreign Military Sales，简称FMS)机制向日本、台湾、韩国和菲律宾出售武器过程中出现的延误问题，并评估这些延误如何影响五角大楼在第一岛链构建、部署和维持强大拒止防御体系(denial defense)的能力。 法案还授权并延长“太平洋威慑倡议”(Pacific Deterrence Initiative)，继续强化美国在印太地区的军事存在与威慑能力，以应对中国不断增长的军事影响力。此外，法案将五角大楼每年向国会提交《中国军事力量报告》(China Military Power Report)的要求延长至2032年1月31日。 鉴于中国近年来持续加强在南中国海的军事活动，法案要求五角大楼制定一项“南中国海危机管理战略”，以提升美国及其盟友应对地区突发事件和军事摩擦的能力。 法案同时要求提交一份报告，详细说明自2025年5月1日以来，原先分配或指派给美国印太司令部（INDOPACOM）的人员、作战平台、装备、弹药及其他军事资源被调往其他作战司令部的情况。此项要求反映出部分国会议员对印太地区资源配置变化的关注，以及对美国维持印太地区军事优先地位的重视。 众院版本强调国防供应链 另一方面，众议院军事委员会已于上星期完成法案审议，通过编号为H.R. 8800的2027财年《国防授权法》。 根据众议院军事委员会通过的版本，法案将国防供应链安全列为重点议题之一，尤其关注关键矿产供应链的韧性。法案指出，中国掌握全球约90%的关键矿产提炼产能，对美国国防工业基础和供应链安全构成重大风险。为降低相关依赖，委员会纳入条款，授权在美国境内建立涵盖关键矿产开采、加工、提炼及回收等领域的劳动力发展计划，以增强本土生产能力。 在印太战略部署方面，众议院版本的法案延续近年来的政策方向，继续强化美国及其盟友应对中国军事挑战的威慑与防御架构。 目前，参众两院版本的《国防授权法》在部分项目授权等方面仍存在若干分歧。未来数月，两院将在分别完成审议后进入协调阶段，就相关条文展开协商并制定统一版本。该版本随后仍须获得参、众两院最终批准，并经总统签署后方可成为法律""",

    }

    for name, text in cases.items():
        print("=" * 60)
        print(f"[{name}]  原文长度={len(text)}")
        chunks = chunk_document(text,chunk_size=800,chunk_overlap=100)
        print(f"  → 切出 {len(chunks)} 块，长度分布：{[len(c) for c in chunks]}")
        for i, c in enumerate(chunks[:50]):
            preview = c.replace("\n", "⏎")
            print(f"  [{i}] {preview}")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    _demo()

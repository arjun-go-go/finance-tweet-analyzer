"""
RAG 文本分块模块
============================================================
职责：将不同来源的文本（文档、推文、分析报告）切分为适合向量化的小块。

设计决策：
- 优先使用 LangChain 的 RecursiveCharacterTextSplitter，按优先级递归尝试
  不同分隔符，保证语义完整性
- 若加载失败（例如 Windows 上 pyarrow DLL 导致段错误），自动回退到
  纯 Python 实现 `_split_text_recursive`，逻辑等价
- 分隔符列表包含中文标点（。！？），适配中英文混合内容
- chunk_size / chunk_overlap 由调用方传入，本模块不引入 settings 依赖，
  保持纯函数风格，便于单元测试
- 短推文（≤ 500 字）直接作为单个 chunk 返回
- 长推文（> 500 字，如中文 KOL 长帖）走递归分块，chunk_size=500 overlap=50
- RAG 专属文本清洗：去除中文字间异常空格、不可见字符、多余换行

在管线中的位置：
  上传/采集 → 解析(PDF/HTML) → **chunk** → embedding → vector store
"""

from __future__ import annotations

import re

# 企业级中文递归切分分隔符（优先级从高到低）
_SEPARATORS = [
    "\n\n",                           # 1. 双换行（段落级）
    "\n",                             # 2. 单换行（行级）
    "。", "！", "？", "；",            # 3. 中文句末/句中标点
    ". ", "! ", "? ", "; ",           # 4. 英文句末标点（带空格，避免切断小数/缩写）
    "，", ", ",                       # 5. 逗号级
    " ",                              # 6. 空格
    "",                               # 7. 兜底：按字符切分
]

# 结构感知正则：匹配推文中常见的列表序号（如 1、 2. 1) (1) 一、 - * 等）
_STRUCTURE_PATTERN = re.compile(
    r'(?m)^(?=\d+[、\.\)]\s*|[一二三四五六七八九十]+[、\.]\s*|[-*]\s+|\(\d+\)\s*)'
)

# 中文字间异常空格正则：前面是中文，后面也是中文，中间的 \s+ 全部替换为空
_ZH_SPACE_PATTERN = re.compile(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])')

# 不可见控制字符正则
_INVISIBLE_PATTERN = re.compile(
    r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200d\ufeff]'
)

# 连续换行符压缩正则
_MULTI_NEWLINE_PATTERN = re.compile(r'\n{3,}')

# 最小 chunk 长度：低于此值的残块丢弃
_MIN_CHUNK_LENGTH = 10

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    _HAS_LANGCHAIN_SPLITTER = True
except Exception:  # pragma: no cover
    _HAS_LANGCHAIN_SPLITTER = False


# ============================================================
# 文本清洗
# ============================================================

def clean_text_for_rag(text: str) -> str:
    """RAG 专属文本清洗：去除无意义空格、规范化换行、清除不可见字符。"""
    if not text:
        return ""

    # 1. 清除零宽字符、BOM 头等不可见控制字符
    text = _INVISIBLE_PATTERN.sub('', text)

    # 2. 去除两个中文字符之间的异常空格 (修复 "公 布" -> "公布")
    text = _ZH_SPACE_PATTERN.sub('', text)

    # 3. 规范化换行符：3 个及以上连续换行压缩为 2 个
    text = _MULTI_NEWLINE_PATTERN.sub('\n\n', text)

    # 4. 去除每行首尾多余空格（保留行内英文单词空格）
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


# ============================================================
# 纯 Python 递归分块 fallback
# ============================================================

def _split_text_recursive(
    text: str, separators: list[str], chunk_size: int, chunk_overlap: int
) -> list[str]:
    """纯 Python 递归分块 fallback（修复了 overlap 导致 chunk 超长的 bug）。"""
    if len(text) <= chunk_size:
        return [text]

    sep = ""
    for s in separators:
        if s in text:
            sep = s
            break

    remaining_seps = separators[separators.index(sep) + 1:] if sep in separators else []

    if sep == "":
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - chunk_overlap if end < len(text) and chunk_overlap > 0 else end
        return chunks

    parts = text.split(sep)
    raw_chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = current + sep + part if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                if len(current) <= chunk_size:
                    raw_chunks.append(current)
                else:
                    raw_chunks.extend(_split_text_recursive(current, remaining_seps, chunk_size, chunk_overlap))
            current = part

    if current:
        if len(current) <= chunk_size:
            raw_chunks.append(current)
        else:
            raw_chunks.extend(_split_text_recursive(current, remaining_seps, chunk_size, chunk_overlap))

    if chunk_overlap > 0 and len(raw_chunks) > 1:
        overlapped: list[str] = [raw_chunks[0]]
        for i in range(1, len(raw_chunks)):
            prev = raw_chunks[i - 1]
            curr = raw_chunks[i]
            overlap_text = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            merged = overlap_text + curr

            if len(merged) > chunk_size:
                allowed_overlap_len = chunk_size - len(curr)
                if allowed_overlap_len > 0:
                    overlap_text = overlap_text[-allowed_overlap_len:]
                    merged = overlap_text + curr
                else:
                    merged = curr

            overlapped.append(merged)
        return overlapped

    return raw_chunks


# ============================================================
# 结构感知 & 合并
# ============================================================

def _pre_split_by_structure(text: str) -> list[str]:
    """结构感知预切分：按显式的逻辑结构（如 1、 2. -）进行粗切，保护金融逻辑链。"""
    parts = _STRUCTURE_PATTERN.split(text)
    return [p.strip() for p in parts if p.strip()]


def _merge_small_chunks(
    chunks: list[str], chunk_size: int, sep: str = "\n", min_chunk_size: int = 50
) -> list[str]:
    """贪心合并相邻短块，并消除低于 min_chunk_size 的碎片。"""
    if not chunks:
        return []
    merged: list[str] = []
    buf = chunks[0]
    for c in chunks[1:]:
        candidate = buf + sep + c
        if len(candidate) <= chunk_size:
            buf = candidate
        else:
            merged.append(buf)
            buf = c
    merged.append(buf)

    if min_chunk_size > 0 and len(merged) > 1:
        final: list[str] = []
        i = 0
        while i < len(merged):
            cur = merged[i]
            if len(cur) < min_chunk_size:
                if final and len(final[-1] + sep + cur) <= chunk_size:
                    final[-1] = final[-1] + sep + cur
                elif i + 1 < len(merged) and len(cur + sep + merged[i + 1]) <= chunk_size:
                    merged[i + 1] = cur + sep + merged[i + 1]
                else:
                    final.append(cur)
            else:
                final.append(cur)
            i += 1
        return final

    return merged


# ============================================================
# 公开 API
# ============================================================

def chunk_document(
    text: str, *, chunk_size: int, chunk_overlap: int
) -> list[str]:
    """将长文本递归分块。

    流程：文本清洗 → 递归切分 → 后置过滤（去空白/残块）。

    Args:
        text: 待分块的原始文本
        chunk_size: 每块最大字符数（len() 计算，中文每字算 1）
        chunk_overlap: 相邻块之间的重叠字符数，用于保持上下文连贯

    Returns:
        分块后的文本列表（已去除首尾空白，过滤 <10 字残块）
    """
    if not text or not text.strip():
        return []
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    # 文本清洗：消除脏数据
    text = clean_text_for_rag(text)

    if _HAS_LANGCHAIN_SPLITTER:
        splitter = RecursiveCharacterTextSplitter(
            separators=_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            keep_separator=True,
        )
        raw = splitter.split_text(text)
    else:
        raw = _split_text_recursive(text, _SEPARATORS, chunk_size, chunk_overlap)

    # 后置过滤：去除空白块和过短残块
    minimum_length = min(_MIN_CHUNK_LENGTH, max(1, chunk_size // 2))
    return [
        c.strip()
        for c in raw
        if c.strip() and len(c.strip()) >= minimum_length
    ]


def _clean_tweet_text(text: str) -> str:
    """推文轻量级清洗：压缩多余换行，提高段落分隔符命中率。"""
    text = _MULTI_NEWLINE_PATTERN.sub('\n\n', text)
    return text.strip()


def chunk_tweet(
    text: str,
    *,
    long_tweet_threshold: int = 500,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    """推文分块：引入结构感知与轻量清洗，保护宏观分析的逻辑链条。"""
    if not text or not text.strip():
        return []

    text = _clean_tweet_text(text)

    # 短/中推文路由：直接作为单个 chunk
    if len(text) <= long_tweet_threshold:
        return [text]

    # 长推文路由：结构感知预切分 → 递归兜底 → 合并相邻短块
    structural_parts = _pre_split_by_structure(text)

    final_chunks = []
    for part in structural_parts:
        if len(part) <= chunk_size:
            final_chunks.append(part)
        else:
            final_chunks.extend(chunk_document(part, chunk_size=chunk_size, chunk_overlap=chunk_overlap))

    return _merge_small_chunks(final_chunks, chunk_size)


def chunk_analysis(text: str, chunk_size: int) -> list[str]:
    """分析结果分块：不设重叠（分析已结构化，无需跨块语境）。"""
    return chunk_document(text, chunk_size=chunk_size, chunk_overlap=0)


def char_count(s: str) -> int:
    """字符计数，用于写入 doc_chunks 表的 char_count 字段。"""
    return len(s) if s else 0

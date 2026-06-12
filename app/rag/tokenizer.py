"""
jieba 分词工具 — 适配 PostgreSQL tsvector 全文检索
============================================================
职责：将中英文混合文本分词为空格分隔的 token 字符串，
     供 PG 的 to_tsvector('simple', ...) 构建倒排索引。

设计决策：
- 使用 jieba 精确模式切分中文（精确模式召回率高于搜索模式）
- 英文转小写后按空格/标点拆分，保留完整单词
- 过滤：停用词 + 单字符 token + 纯数字 + 纯标点
- 使用 'simple' 配置而非 'chinese'：因为分词已由 jieba 完成，
  PG 只负责存储和匹配，不再做任何语言处理

在管线中的位置：
  写入：chunk_text → tokenize_for_tsvector → to_tsvector('simple', result) → PG 存储
  查询：user_query → tokenize_for_tsquery → plainto_tsquery('simple', result) → PG 匹配
"""

from __future__ import annotations

import re
import string

import jieba

jieba.add_word("英伟达", freq=100000)
jieba.add_word("特斯拉", freq=100000)
jieba.add_word("比特币", freq=100000)
jieba.add_word("以太坊", freq=100000)
jieba.add_word("区块链", freq=100000)
jieba.add_word("半导体", freq=100000)
jieba.add_word("芯片", freq=100000)
jieba.add_word("光模块", freq=100000)
jieba.add_word("量化宽松", freq=100000)
jieba.add_word("做空", freq=100000)
jieba.add_word("做多", freq=100000)
jieba.add_word("利空", freq=100000)
jieba.add_word("利好", freq=100000)
jieba.add_word("看涨", freq=100000)
jieba.add_word("看跌", freq=100000)
jieba.add_word("加密货币", freq=100000)
jieba.add_word("碳化硅", freq=100000)
jieba.add_word("氮化镓", freq=100000)

_PUNCT_RE = re.compile(r"[{}]+".format(re.escape(
    string.punctuation + "。！？，、；：""''（）【】《》…—·～\n\r\t"
)))

_STOPWORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "们", "那", "些", "么", "什么", "吗", "呢", "吧", "啊", "哦",
    "被", "把", "让", "与", "及", "或", "而", "但", "如果", "因为",
    "所以", "可以", "这个", "那个", "还", "已经", "还是", "又",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "and",
    "but", "or", "nor", "not", "so", "if", "then", "than", "that",
    "this", "these", "those", "it", "its", "i", "me", "my", "we",
    "our", "you", "your", "he", "his", "she", "her", "they", "their",
}


def _is_valid_token(token: str) -> bool:
    if len(token) <= 1:
        return False
    if token.isdigit():
        return False
    if token in _STOPWORDS:
        return False
    return True


_SEGMENT_RE = re.compile(r"([a-zA-Z0-9][a-zA-Z0-9./]*[a-zA-Z0-9]|[a-zA-Z0-9]+)")


def tokenize_for_tsvector(text: str) -> str:
    """将文本分词为空格分隔的 token 字符串，适配 PG to_tsvector('simple', ...)。

    策略：先用正则提取英文/数字 token，剩余中文部分用 jieba 切分，
    避免 jieba 将英文字母与相邻中文混合切割。

    示例：
        >>> tokenize_for_tsvector("英伟达芯片需求增长，NVDA股价上涨")
        "英伟达 芯片 需求 增长 nvda 股价 上涨"
    """
    if not text:
        return ""
    text = _PUNCT_RE.sub(" ", text)
    result: list[str] = []
    last_end = 0

    for m in _SEGMENT_RE.finditer(text):
        # 处理英文 token 前的中文片段
        cn_part = text[last_end:m.start()]
        if cn_part.strip():
            for token in jieba.cut(cn_part, cut_all=False):
                t = token.strip().lower()
                if _is_valid_token(t):
                    result.append(t)
        # 处理英文 token
        en_token = m.group().lower()
        if _is_valid_token(en_token):
            result.append(en_token)
        last_end = m.end()

    # 处理末尾的中文片段
    tail = text[last_end:]
    if tail.strip():
        for token in jieba.cut(tail, cut_all=False):
            t = token.strip().lower()
            if _is_valid_token(t):
                result.append(t)

    return " ".join(result)


def tokenize_for_tsquery(query: str) -> str:
    """将用户查询分词为适合 plainto_tsquery 的格式。

    与 tokenize_for_tsvector 逻辑相同，保证查询和索引使用一致的分词策略。
    """
    return tokenize_for_tsvector(query)

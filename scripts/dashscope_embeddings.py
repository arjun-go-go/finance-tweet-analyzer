"""DashScope Embeddings 连通性测试脚本。

用法（在项目根目录 finance-tweet-analyzer 下）：
    uv run python scripts/test_dashscope_embeddings.py

读取顺序：
    1. 命令行参数 --api-key
    2. 环境变量 DASHSCOPE_API_KEY
    3. app/core/config.py 中的 settings.dashscope_api_key（来自 .env）
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# 确保能 import 项目根下的 app 包（无论从哪个 cwd 运行）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from langchain_community.embeddings import DashScopeEmbeddings


def _load_api_key(cli_key: str | None) -> str:
    if cli_key:
        return cli_key
    env_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        from app.core.config import settings  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"无法导入 settings: {e}")
    return (settings.dashscope_api_key or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="DashScope Embeddings 测试")
    parser.add_argument("--api-key", default=None, help="DashScope API Key（可选）")
    parser.add_argument(
        "--model",
        default=os.environ.get("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4"),
        help="模型名（默认 text-embedding-v4，也可用 text-embedding-v1/v2/v3）",
    )
    parser.add_argument(
        "--text",
        default="你好，通义千问！这是一条测试文本。",
        help="待向量化的文本",
    )
    parser.add_argument("--batch", action="store_true", help="同时测试 embed_documents 批量接口")
    args = parser.parse_args()

    api_key = _load_api_key(args.api_key)
    if not api_key:
        print("[FAIL] 未找到 DASHSCOPE_API_KEY，请通过 --api-key / 环境变量 / .env 任一方式提供")
        return 2

    print(f"[INFO] model        = {args.model}")
    print(f"[INFO] api_key      = {api_key[:6]}...{api_key[-4:]} (len={len(api_key)})")
    print(f"[INFO] text         = {args.text!r}")

    embedder = DashScopeEmbeddings(model=args.model, dashscope_api_key=api_key)

    # 单条
    t0 = time.perf_counter()
    try:
        vec = embedder.embed_query(args.text)
        print(len(vec))
    except Exception as e:
        print(f"[FAIL] embed_query 异常: {type(e).__name__}: {e}")
        return 1
    cost = (time.perf_counter() - t0) * 1000
    print(f"[OK] embed_query: dim={len(vec)} cost={cost:.1f}ms head={vec[:5]}")

    # 批量
    if args.batch:
        docs = [args.text, "BTC 比特币价格分析", "Apple Q3 earnings beat"]
        t0 = time.perf_counter()
        try:
            vecs = embedder.embed_documents(docs)
        except Exception as e:
            print(f"[FAIL] embed_documents 异常: {type(e).__name__}: {e}")
            return 1
        cost = (time.perf_counter() - t0) * 1000
        print(
            f"[OK] embed_documents: count={len(vecs)} dims={[len(v) for v in vecs]} "
            f"cost={cost:.1f}ms"
        )

    print("[DONE] DashScope Embeddings 通讯正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())

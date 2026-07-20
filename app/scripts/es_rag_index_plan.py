"""Print the approved Elasticsearch RAG index creation plan.

This script is read-only. It does not create or modify Elasticsearch state.
"""

from __future__ import annotations

import json

from app.core.config import settings
from app.rag.keyword_store import build_rag_index_body


def main() -> None:
    plan = {
        "index": settings.es_rag_index,
        "elasticsearch_url": settings.elasticsearch_url,
        "body": build_rag_index_body(),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

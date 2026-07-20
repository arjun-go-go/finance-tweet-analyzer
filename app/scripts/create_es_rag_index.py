"""Create the approved Elasticsearch RAG index explicitly."""

from __future__ import annotations

from app.rag.keyword_store import get_keyword_store


def main() -> None:
    store = get_keyword_store()
    created = store.create_index_if_missing()
    print({"index": store.index_name, "created": created})


if __name__ == "__main__":
    main()

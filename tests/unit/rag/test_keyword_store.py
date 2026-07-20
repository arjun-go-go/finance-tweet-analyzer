from datetime import datetime, timezone
from uuid import UUID

from app.rag.keyword_store import (
    ElasticsearchKeywordStore,
    build_rag_index_body,
    chunk_to_es_document,
)


class FakeIndices:
    def __init__(self):
        self.exists_calls = []
        self.create_calls = []
        self.exists_result = False

    def exists(self, index):
        self.exists_calls.append(index)
        return self.exists_result

    def create(self, index, **body):
        self.create_calls.append({"index": index, **body})
        return {"acknowledged": True}


class FakeClient:
    def __init__(self, hits=None):
        self.indices = FakeIndices()
        self.search_calls = []
        self.ping_calls = 0
        self.hits = hits or []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {"hits": {"hits": self.hits}}

    def ping(self):
        self.ping_calls += 1
        return True


def test_rag_index_body_uses_ik_analyzers_for_content_and_title():
    body = build_rag_index_body()

    assert body["settings"]["analysis"]["analyzer"]["ik_max_word_analyzer"] == {
        "type": "custom",
        "tokenizer": "ik_max_word",
    }
    assert body["mappings"]["properties"]["content"] == {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart",
    }
    assert body["mappings"]["properties"]["title"]["fields"]["keyword"] == {"type": "keyword"}


def test_search_query_filters_public_and_current_user_private_chunks():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    store.search(
        query_text="BTC ETF 风险",
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
        blogger_filter=["satoshi"],
        time_range_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_range_end=datetime(2026, 1, 31, tzinfo=timezone.utc),
        top_k=7,
    )

    call = client.search_calls[0]
    assert call["index"] == "finance_rag_chunks"
    assert call["size"] == 7
    filters = call["query"]["bool"]["filter"]
    assert {"terms": {"blogger_handle": ["satoshi"]}} in filters
    assert {"range": {"published_at": {"gte": "2026-01-01T00:00:00+00:00"}}} in filters
    assert {"range": {"published_at": {"lte": "2026-01-31T00:00:00+00:00"}}} in filters
    visibility_filter = filters[0]["bool"]["should"]
    assert {"term": {"visibility": "public"}} in visibility_filter
    assert {
        "bool": {
            "must": [
                {"term": {"visibility": "private"}},
                {"term": {"user_id": "10000000-0000-0000-0000-000000000001"}},
            ]
        }
    } in visibility_filter


def test_search_query_without_user_id_only_searches_public_chunks():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    store.search(query_text="BTC", user_id=None)

    filters = client.search_calls[0]["query"]["bool"]["filter"]
    assert filters[0] == {"term": {"visibility": "public"}}


def test_search_converts_hits_to_rag_result_shape():
    client = FakeClient(
        hits=[
            {
                "_id": "chunk-1",
                "_score": 3.25,
                "_source": {
                    "chunk_id": "chunk-1",
                    "content": "BTC risk text",
                    "source_type": "tweet",
                    "metadata": {"ticker": "BTC"},
                },
            }
        ]
    )
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    results = store.search(query_text="BTC", user_id=None)

    assert results == [
        {
            "unique_id": "es:chunk-1",
            "content": "BTC risk text",
            "source_type": "tweet",
            "metadata": {"ticker": "BTC", "chunk_id": "chunk-1"},
            "score": 3.25,
        }
    ]


def test_create_index_uses_approved_mapping_and_does_not_recreate_existing_index():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    created = store.create_index_if_missing()
    second_created = store.create_index_if_missing()

    assert created is True
    assert second_created is True
    assert client.indices.create_calls[0]["index"] == "finance_rag_chunks"
    assert client.indices.create_calls[0]["mappings"] == build_rag_index_body()["mappings"]


def test_chunk_to_es_document_derives_visibility_and_fields():
    class Chunk:
        id = UUID("20000000-0000-0000-0000-000000000001")
        document_id = UUID("30000000-0000-0000-0000-000000000001")
        chunk_index = 2
        content = "content"
        metadata_ = {
            "source_type": "document",
            "title": "Report",
            "source_uri": "https://example.com/report",
            "tickers": "BTC,ETH",
        }
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    doc = chunk_to_es_document(
        Chunk(),
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
    )

    assert doc["chunk_id"] == "20000000-0000-0000-0000-000000000001"
    assert doc["document_id"] == "30000000-0000-0000-0000-000000000001"
    assert doc["user_id"] == "10000000-0000-0000-0000-000000000001"
    assert doc["visibility"] == "private"
    assert doc["source_type"] == "document"
    assert doc["tickers"] == ["BTC", "ETH"]
    assert doc["ticker"] == "BTC"
    assert doc["title"] == "Report"
    assert doc["url"] == "https://example.com/report"

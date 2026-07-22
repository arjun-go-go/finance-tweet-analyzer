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
        self.alias_calls = []
        self.get_alias_calls = []
        self.update_aliases_calls = []
        self.delete_calls = []
        self.exists_result = False
        self.alias_exists_result = False
        self.alias_map = {}

    def exists(self, index):
        self.exists_calls.append(index)
        return self.exists_result

    def exists_alias(self, name):
        self.alias_calls.append(name)
        return self.alias_exists_result

    def get_alias(self, name):
        self.get_alias_calls.append(name)
        return self.alias_map

    def update_aliases(self, body):
        self.update_aliases_calls.append(body)
        for action in body.get("actions", []):
            if "add" in action:
                data = action["add"]
                self.alias_exists_result = True
                self.alias_map = {
                    data["index"]: {"aliases": {data["alias"]: {}}},
                }
        return {"acknowledged": True}

    def create(self, index, **body):
        self.create_calls.append({"index": index, **body})
        return {"acknowledged": True}

    def delete(self, index):
        self.delete_calls.append(index)
        return {"acknowledged": True}


class FakeClient:
    def __init__(self, hits=None):
        self.indices = FakeIndices()
        self.search_calls = []
        self.delete_by_query_calls = []
        self.reindex_calls = []
        self.ping_calls = 0
        self.hits = hits or []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {"hits": {"hits": self.hits}}

    def ping(self):
        self.ping_calls += 1
        return True

    def delete_by_query(self, **kwargs):
        self.delete_by_query_calls.append(kwargs)
        return {"deleted": 2}

    def reindex(self, **kwargs):
        self.reindex_calls.append(kwargs)
        return {"created": 3}


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
    assert body["mappings"]["properties"]["index_stage"] == {"type": "keyword"}


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
    filters = call["query"]["function_score"]["query"]["bool"]["filter"]
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

    filters = client.search_calls[0]["query"]["function_score"]["query"]["bool"]["filter"]
    assert filters[0] == {"term": {"visibility": "public"}}


def test_search_query_uses_weighted_fields_stage_boost_and_time_decay():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    store.search(query_text="NVDA risk", user_id=None)

    query = client.search_calls[0]["query"]["function_score"]
    multi_match = query["query"]["bool"]["must"][0]["multi_match"]
    assert "ticker^8" in multi_match["fields"]
    assert "tickers^8" in multi_match["fields"]
    assert "blogger_handle^3" in multi_match["fields"]
    assert "content^2" in multi_match["fields"]
    assert {"filter": {"term": {"index_stage": "analysis"}}, "weight": 1.25} in query["functions"]
    assert {
        "gauss": {
            "published_at": {
                "origin": "now",
                "scale": "14d",
                "decay": 0.5,
            }
        },
        "weight": 1.15,
    } in query["functions"]


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
                "highlight": {"content": ["BTC <em>risk</em> text"]},
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
            "metadata": {
                "ticker": "BTC",
                "chunk_id": "chunk-1",
                "highlight": {"content": ["BTC <em>risk</em> text"]},
            },
            "score": 3.25,
        }
    ]


def test_debug_search_returns_query_and_raw_hits_with_highlight():
    client = FakeClient(
        hits=[
            {
                "_id": "chunk-1",
                "_score": 3.25,
                "_source": {"chunk_id": "chunk-1", "content": "BTC risk text"},
                "highlight": {"content": ["BTC <em>risk</em> text"]},
            }
        ]
    )
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    debug = store.debug_search(query_text="BTC risk", user_id=None, top_k=5)

    assert debug["index"] == "finance_rag_chunks"
    assert debug["query"] == client.search_calls[0]["query"]
    assert debug["raw_hits"][0]["highlight"] == {"content": ["BTC <em>risk</em> text"]}
    assert debug["results"][0]["unique_id"] == "es:chunk-1"


def test_create_index_uses_approved_mapping_and_does_not_recreate_existing_index():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    created = store.create_index_if_missing()
    second_created = store.create_index_if_missing()

    assert created is True
    assert second_created is False
    assert client.indices.create_calls[0]["index"] == "finance_rag_chunks_v1"
    assert client.indices.create_calls[0]["mappings"] == build_rag_index_body()["mappings"]


def test_create_index_bootstraps_versioned_index_and_alias_when_alias_missing():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    created = store.create_index_if_missing()

    assert created is True
    assert client.indices.create_calls[0]["index"] == "finance_rag_chunks_v1"
    assert client.indices.update_aliases_calls[0] == {
        "actions": [{"add": {"index": "finance_rag_chunks_v1", "alias": "finance_rag_chunks"}}]
    }


def test_create_index_does_not_recreate_when_alias_exists():
    client = FakeClient()
    client.indices.alias_exists_result = True
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    created = store.create_index_if_missing()

    assert created is False
    assert client.indices.create_calls == []


def test_create_index_migrates_existing_concrete_index_to_versioned_alias():
    client = FakeClient()
    client.indices.exists_result = True
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    created = store.create_index_if_missing()

    assert created is True
    assert client.indices.create_calls[0]["index"] == "finance_rag_chunks_v1"
    assert client.reindex_calls[0] == {
        "source": {"index": "finance_rag_chunks"},
        "dest": {"index": "finance_rag_chunks_v1"},
        "refresh": True,
        "wait_for_completion": True,
    }
    assert client.indices.delete_calls == ["finance_rag_chunks"]
    assert client.indices.update_aliases_calls[0] == {
        "actions": [{"add": {"index": "finance_rag_chunks_v1", "alias": "finance_rag_chunks"}}]
    }


def test_switch_alias_replaces_old_version_with_new_version():
    client = FakeClient()
    client.indices.alias_map = {
        "finance_rag_chunks_v1": {"aliases": {"finance_rag_chunks": {}}},
    }
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    store.switch_alias("finance_rag_chunks_v2")

    assert client.indices.update_aliases_calls[0] == {
        "actions": [
            {"remove": {"index": "finance_rag_chunks_v1", "alias": "finance_rag_chunks"}},
            {"add": {"index": "finance_rag_chunks_v2", "alias": "finance_rag_chunks"}},
        ]
    }


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


def test_delete_by_source_deletes_matching_source_documents():
    client = FakeClient()
    store = ElasticsearchKeywordStore(client=client, index_name="finance_rag_chunks")

    result = store.delete_by_source("tweet", "tweet-1")

    assert result == {"deleted": 2}
    assert client.delete_by_query_calls[0] == {
        "index": "finance_rag_chunks",
        "query": {
            "bool": {
                "filter": [
                    {"term": {"source_type": "tweet"}},
                    {"term": {"source_id": "tweet-1"}},
                ]
            }
        },
        "conflicts": "proceed",
        "refresh": True,
    }

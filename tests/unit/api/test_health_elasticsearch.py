from app.api import router as router_module


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, stmt):
        return None


class FakeEngine:
    def connect(self):
        return FakeConnection()


class FakeRedis:
    def ping(self):
        return True


class FakeVectorStore:
    def count(self, collection):
        return 1


def test_elasticsearch_health_check_is_optional(monkeypatch):
    import app.core.deps as deps
    import app.rag.keyword_store as keyword_store
    import app.rag.vector_store as vector_store
    import app.scheduler.locks as locks

    monkeypatch.setattr(deps, "engine", FakeEngine())
    monkeypatch.setattr(locks, "_get_redis", lambda: FakeRedis())
    monkeypatch.setattr(vector_store, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(router_module.settings, "rag_keyword_backend", "elasticsearch")
    monkeypatch.setattr(router_module.settings, "elasticsearch_url", "http://localhost:9200")
    monkeypatch.setattr(
        keyword_store,
        "get_keyword_store",
        lambda: (_ for _ in ()).throw(RuntimeError("es down")),
    )

    result = router_module.health_check()

    assert result["status"] == "ok"
    assert result["checks"]["database"] == "ok"
    assert result["checks"]["redis"] == "ok"
    assert result["checks"]["vector_store"] == "ok"
    assert result["checks"]["elasticsearch"] == "error: es down"

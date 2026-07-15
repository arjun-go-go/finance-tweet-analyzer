import uuid


class TestConversationCreate:
    def test_create_conversation(self, client, auth):
        client.headers.update(auth.headers("test_user"))
        resp = client.post(
            "/api/chat/conversations",
            json={"user_id": "test_user", "title": "测试会话", "metadata": {}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == auth.user_id("test_user")
        assert data["title"] == "测试会话"
        assert data["status"] == "active"
        assert data["message_count"] == 0

    def test_create_conversation_no_title(self, client, auth):
        client.headers.update(auth.headers("test_user"))
        resp = client.post(
            "/api/chat/conversations", json={"user_id": "test_user"}
        )
        assert resp.status_code == 201
        assert resp.json()["title"] is None


class TestConversationList:
    def test_list_empty(self, client, auth):
        client.headers.update(auth.headers("nobody"))
        resp = client.get(
            "/api/chat/conversations", params={"user_id": "nobody"}
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["has_more"] is False

    def test_list_returns_user_conversations(self, client, auth):
        client.headers.update(auth.headers("u1"))
        client.post("/api/chat/conversations", json={"user_id": "u1"})
        client.post(
            "/api/chat/conversations",
            json={"user_id": "u1", "title": "Second"},
        )
        client.headers.update(auth.headers("u2"))
        client.post("/api/chat/conversations", json={"user_id": "u2"})

        client.headers.update(auth.headers("u1"))
        resp = client.get(
            "/api/chat/conversations", params={"user_id": "u1"}
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert all(item["status"] == "active" for item in items)

    def test_list_pagination(self, client, auth):
        client.headers.update(auth.headers("pager"))
        for _ in range(5):
            client.post("/api/chat/conversations", json={"user_id": "pager"})

        resp = client.get(
            "/api/chat/conversations",
            params={"user_id": "pager", "limit": 3},
        )
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["has_more"] is True
        assert data["next_cursor"] is not None


class TestConversationGetUpdateDelete:
    def test_get_conversation(self, client, auth):
        client.headers.update(auth.headers("u1"))
        create_resp = client.post(
            "/api/chat/conversations",
            json={"user_id": "u1", "title": "T"},
        )
        conv_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/chat/conversations/{conv_id}", params={"user_id": "u1"}
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "T"

    def test_get_nonexistent(self, client, auth):
        client.headers.update(auth.headers("u1"))
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/chat/conversations/{fake_id}", params={"user_id": "u1"}
        )
        assert resp.status_code == 404

    def test_get_wrong_user(self, client, auth):
        client.headers.update(auth.headers("owner"))
        create_resp = client.post(
            "/api/chat/conversations", json={"user_id": "owner"}
        )
        conv_id = create_resp.json()["id"]

        client.headers.update(auth.headers("intruder"))
        resp = client.get(
            f"/api/chat/conversations/{conv_id}",
            params={"user_id": "intruder"},
        )
        assert resp.status_code == 404

    def test_update_title(self, client, auth):
        client.headers.update(auth.headers("u1"))
        create_resp = client.post(
            "/api/chat/conversations", json={"user_id": "u1"}
        )
        conv_id = create_resp.json()["id"]

        resp = client.patch(
            f"/api/chat/conversations/{conv_id}",
            json={"title": "新标题"},
            params={"user_id": "u1"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "新标题"

    def test_delete_soft(self, client, auth):
        client.headers.update(auth.headers("u1"))
        create_resp = client.post(
            "/api/chat/conversations", json={"user_id": "u1"}
        )
        conv_id = create_resp.json()["id"]

        resp = client.delete(
            f"/api/chat/conversations/{conv_id}", params={"user_id": "u1"}
        )
        assert resp.status_code == 204

        resp = client.get(
            f"/api/chat/conversations/{conv_id}", params={"user_id": "u1"}
        )
        assert resp.status_code == 404

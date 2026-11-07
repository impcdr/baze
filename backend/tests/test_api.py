import re

import falcon
from falcon import testing

TOKEN = {"Authorization": "Bearer test-token-test-token"}


def test_health_and_discovery(client):
    result = testing.TestClient(client).simulate_get("/api/health")
    assert result.status_code == 200
    assert result.json["mongo"] == "ok"
    assert result.json["frontend"] == "ready"

    info = testing.TestClient(client).simulate_get("/api")
    assert info.status_code == 200
    assert info.json["chat"] == "/chat"
    assert any(item["path"] == "/api/conversations" for item in info.json["endpoints"])


def test_conversations_require_a_bearer_token(client):
    result = testing.TestClient(client).simulate_get("/api/conversations")
    assert result.status_code == 401


def test_conversation_round_trip(client):
    http = testing.TestClient(client)
    created = http.simulate_post("/api/conversations", json={}, headers=TOKEN)
    assert created.status_code == 201
    conversation_id = created.json["id"]
    assert created.json["title"] == "New chat"
    assert created.json["messages"] == []

    posted = http.simulate_post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Rewrite this more clearly"},
        headers=TOKEN,
    )
    assert posted.status_code == 201
    assert posted.json["user"]["role"] == "user"
    assert posted.json["assistant"]["content"].startswith("A clearer version:")
    assert posted.json["conversation"]["title"] == "Rewrite this more clearly"
    assert len(posted.json["conversation"]["messages"]) == 2

    renamed = http.simulate_patch(
        f"/api/conversations/{conversation_id}",
        json={"title": "Draft notes"},
        headers=TOKEN,
    )
    assert renamed.status_code == 200
    assert renamed.json["title"] == "Draft notes"

    listed = http.simulate_get("/api/conversations", query_string="q=draft", headers=TOKEN)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json["conversations"]] == [conversation_id]

    fetched = http.simulate_get(f"/api/conversations/{conversation_id}", headers=TOKEN)
    assert fetched.json["messages"][1]["role"] == "assistant"

    removed = http.simulate_delete(f"/api/conversations/{conversation_id}", headers=TOKEN)
    assert removed.status_code == 204
    missing = http.simulate_get(f"/api/conversations/{conversation_id}", headers=TOKEN)
    assert missing.status_code == 404


def test_rejects_blank_messages_and_unknown_ids(client):
    http = testing.TestClient(client)
    created = http.simulate_post("/api/conversations", json={"title": "Kept"}, headers=TOKEN)
    conversation_id = created.json["id"]
    blank = http.simulate_post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "   "},
        headers=TOKEN,
    )
    assert blank.status_code == 400
    missing = http.simulate_post(
        "/api/conversations/not-a-uuid/messages",
        json={"content": "Hello"},
        headers=TOKEN,
    )
    assert missing.status_code == 404


def test_hosted_frontend_and_chat_route(client):
    http = testing.TestClient(client)
    home = http.simulate_get("/")
    assert home.status_code == 200
    assert b"<app-root>" in home.content
    assert "text/html" in home.headers["content-type"]

    chat = http.simulate_get("/chat")
    assert chat.status_code == 200
    assert chat.content == home.content

    match = re.search(br'src="([^"]+\.js)"', home.content)
    assert match is not None
    script = http.simulate_get("/" + match.group(1).decode())
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]

    escaped = http.simulate_get("/../.env")
    assert escaped.status_code == 404


def test_default_reply_mentions_the_prompt(client):
    http = testing.TestClient(client)
    created = http.simulate_post("/api/conversations", json={}, headers=TOKEN)
    posted = http.simulate_post(
        f"/api/conversations/{created.json['id']}/messages",
        json={"content": "How should I start?"},
        headers=TOKEN,
    )
    assert "How should I start?" in posted.json["assistant"]["content"]


def test_cors_preflight(client):
    result = testing.TestClient(client).simulate_options(
        "/api/conversations",
        headers={"Origin": "http://127.0.0.1:4201", "Access-Control-Request-Method": "POST"},
    )
    assert result.status_code == 204
    assert result.headers["access-control-allow-origin"] == "*"

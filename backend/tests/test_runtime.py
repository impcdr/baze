import json
from dataclasses import replace

from falcon import testing

from baze_api.app import create_app
from baze_api.catalog import STUDIO_ID, WATCHLIST_ID
from baze_api.db import apps, messages
from baze_api.hermes import HermesError
from baze_api.provisioner import ensure_studio
from baze_api.proxy import proxy_request
from baze_api.runtime import RuntimeServices

TOKEN = {"Authorization": "Bearer test-token-test-token"}
VULTR_KEY = "vultr-test-key-should-not-leak"


class FakeDocker:
    def __init__(self):
        self.runs = []
        self.removed = []
        self.started = []
        self.stopped = []

    def run(self, args):
        self.runs.append(list(args))
        return "container-id"

    def remove(self, name):
        self.removed.append(name)

    def exists(self, name):
        return any(name in args for args in self.runs)

    def start(self, name):
        self.started.append(name)

    def stop(self, name):
        self.stopped.append(name)

    def running(self, name):
        return False


class FakeHermes:
    def __init__(self):
        self.calls = []

    def complete(self, *, base_url, api_key, content, session_id):
        self.calls.append(
            {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
        )
        if session_id:
            return "Still here.", session_id
        return "Noted.", "session-1"


def _app(settings, tmp_path, docker, hermes, *, healthy=True, infer=None):
    tuned = replace(
        settings,
        apps_root=tmp_path,
        vultr_api_key=VULTR_KEY,
        health_timeout=0,
        health_interval=0,
        proxy_port=8001,
        memory_mb=512,
    )

    def spawn(fn):
        fn()

    apps(tuned).delete_many({"kind": "runtime"})
    messages(tuned).delete_many({})
    falcon_app = create_app(
        tuned,
        RuntimeServices(docker, hermes, spawn, healthy=lambda _url: healthy, infer=infer),
    )
    return testing.TestClient(falcon_app), tuned


def test_create_starts_a_container_without_the_vultr_key(settings, tmp_path):
    docker = FakeDocker()
    client, tuned = _app(settings, tmp_path, docker, FakeHermes())
    created = client.simulate_post("/api/runtime/apps", json={"name": "Field notes"}, headers=TOKEN)
    assert created.status_code == 201
    assert created.json["status"] == "provisioning"
    assert "proxyToken" not in created.json
    assert "apiServerKey" not in json.dumps(created.json)
    assert VULTR_KEY not in json.dumps(created.json)

    listed = client.simulate_get(f"/api/runtime/apps/{created.json['id']}", headers=TOKEN)
    assert listed.json["status"] == "live"
    assert docker.runs, "docker run was not called"
    args = docker.runs[0]
    assert args.count("512m") == 2
    assert "--cpus" in args and args[args.index("--cpus") + 1] == "1"
    assert "baze-inference:host-gateway" in args
    assert any(
        part.endswith("sha256:adb7890916de63245523492be8f68f9d2095fecbec4e2a6dab7960381f0fc002") for part in args
    )
    assert args[-2:] == ["gateway", "run"]
    joined = " ".join(args)
    assert "VULTR" not in joined
    assert VULTR_KEY not in joined
    config = (tmp_path / created.json["id"] / "config.yaml").read_text()
    assert "base_url: http://baze-inference:8001/v1" in config
    assert VULTR_KEY not in config
    assert "api_key:" in config

    shelf = client.simulate_get("/api/apps")
    assert shelf.json["summary"] == "3 apps on your shelf · 0 live"
    assert all(app["name"] != "Field notes" for app in shelf.json["apps"])


def test_messages_keep_the_session_and_send_only_the_new_turn(settings, tmp_path):
    hermes = FakeHermes()
    client, _tuned = _app(settings, tmp_path, FakeDocker(), hermes)
    created = client.simulate_post("/api/runtime/apps", json={"name": "Notes"}, headers=TOKEN)
    app_id = created.json["id"]
    first = client.simulate_post(
        f"/api/runtime/apps/{app_id}/messages",
        json={"content": "Hello"},
        headers=TOKEN,
    )
    assert first.status_code == 201
    assert first.json["message"]["content"] == "Noted."
    assert first.json["sessionId"] == "session-1"
    second = client.simulate_post(
        f"/api/runtime/apps/{app_id}/messages",
        json={"content": "Continue"},
        headers=TOKEN,
    )
    assert second.json["message"]["content"] == "Still here."
    assert hermes.calls[0]["session_id"] is None
    assert hermes.calls[0]["content"] == "Hello"
    assert hermes.calls[1]["session_id"] == "session-1"
    assert hermes.calls[1]["content"] == "Continue"
    assert hermes.calls[1]["api_key"]
    assert hermes.calls[1]["api_key"] != VULTR_KEY
    history = client.simulate_get(f"/api/runtime/apps/{app_id}/messages", headers=TOKEN)
    assert [turn["role"] for turn in history.json] == ["user", "assistant", "user", "assistant"]


def test_delete_removes_the_container_and_third_app_is_rejected(settings, tmp_path):
    docker = FakeDocker()
    client, _tuned = _app(settings, tmp_path, docker, FakeHermes())
    first = client.simulate_post("/api/runtime/apps", json={"name": "One"}, headers=TOKEN)
    second = client.simulate_post("/api/runtime/apps", json={"name": "Two"}, headers=TOKEN)
    assert first.status_code == 201
    assert second.status_code == 201
    third = client.simulate_post("/api/runtime/apps", json={"name": "Three"}, headers=TOKEN)
    assert third.status_code == 409

    removed = client.simulate_delete(f"/api/runtime/apps/{first.json['id']}", headers=TOKEN)
    assert removed.status_code == 204
    assert docker.removed == [f"baze-app-{first.json['id']}"]
    assert not (tmp_path / first.json["id"]).exists()
    missing = client.simulate_get(f"/api/runtime/apps/{first.json['id']}", headers=TOKEN)
    assert missing.status_code == 404

    again = client.simulate_post("/api/runtime/apps", json={"name": "Three"}, headers=TOKEN)
    assert again.status_code == 201


def _reception(messages):
    system = messages[0]["content"]
    if system.startswith("You write build plans"):
        return "Write the pantry page\nSave it in the box"
    if "JSON object" in system:
        return '{"name":"Pantry","summary":"A list of rice and tea","icon":"lucideUtensils"}'
    return "A list for rice and tea. Press Make."


def test_creating_an_app_hosts_it_and_deletion_removes_the_box(settings, tmp_path):
    docker = FakeDocker()

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append(
                {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
            )
            page = "<!doctype html><html><body><h1>Pantry</h1></body></html>"
            return page, "session-built"

    hermes = PageHermes()
    client, tuned = _app(settings, tmp_path, docker, hermes, infer=_reception)
    talked = client.simulate_post("/api/creator/messages", json={"content": "A pantry list for rice and tea"})
    assert talked.status_code == 200
    assert talked.json["messages"][0]["content"] == "A pantry list for rice and tea"
    assert "Press Make" in talked.json["messages"][1]["content"]
    assert talked.json["sketch"] == {
        "name": "Pantry",
        "summary": "A list of rice and tea",
        "icon": "lucideUtensils",
        "color": "",
    }

    made = client.simulate_post("/api/creator/make")
    assert made.status_code == 201
    app_id = made.json["id"]
    assert len(app_id) == 32
    assert [step["label"] for step in made.json["steps"][:3]] == [
        "Creating the container",
        "Starting the box",
        "Opening the harness",
    ]
    assert made.json["steps"][3]["label"] == "Write the pantry page"
    assert hermes.calls == []
    ready = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert ready.json["status"] == "building"
    assert ready.json["boxReady"] is True
    assert ready.json["name"] == "Pantry"
    assert ready.json["icon"] == "lucideUtensils"
    assert ready.json["messages"][0]["content"] == "A pantry list for rice and tea"
    cleared = client.simulate_get("/api/creator").json
    assert cleared["messages"] == []
    assert cleared["sketch"]["name"] == ""

    built = client.simulate_post(f"/api/apps/{app_id}/build")
    assert built.status_code == 202
    assert len(hermes.calls) == 1
    assert "A pantry list for rice and tea" in hermes.calls[0]["content"]
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.status_code == 200
    assert manage.json["status"] == "live"
    assert "Pantry" in manage.json["messages"][-1]["content"]
    assert all(step["state"] == "done" for step in manage.json["steps"] if step["id"].startswith("plan"))
    page = (tmp_path / app_id / "app" / "index.html").read_text()
    assert "Pantry" in page
    assert "placeholder" not in page
    script = (tmp_path / app_id / "app" / "run.sh").read_text()
    assert "hermes gateway run" in script
    config = (tmp_path / app_id / "config.yaml").read_text()
    assert "base_url: http://baze-inference:8001/v1" in config
    assert VULTR_KEY not in config
    joined = " ".join(docker.runs[-1])
    assert ":8080" in joined and ":8642" in joined
    assert "baze-inference:host-gateway" in joined
    assert joined.endswith("sh /opt/data/app/run.sh")
    assert VULTR_KEY not in joined

    shelf = client.simulate_get("/api/apps")
    assert shelf.json["summary"] == "4 apps on your shelf · 1 live"
    listed = next(app for app in shelf.json["apps"] if app["id"] == app_id)
    assert listed["path"] == f"/{app_id}"
    assert listed["status"] == "live"

    removed = client.simulate_delete(f"/api/apps/{app_id}")
    assert removed.status_code == 204
    assert docker.removed == [f"baze-app-{app_id}"]
    assert not (tmp_path / app_id).exists()
    missing = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert missing.status_code == 404
    studio = client.simulate_delete(f"/api/apps/{STUDIO_ID}")
    assert studio.status_code == 204
    client, _tuned = _app(tuned, tmp_path, docker, PageHermes(), infer=_reception)
    left = client.simulate_get("/api/apps").json["apps"]
    assert all(app["id"] not in {app_id, STUDIO_ID} for app in left)


def test_creator_reset_returns_to_an_empty_reception(settings, tmp_path):
    client, _tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes(), infer=_reception)
    client.simulate_post("/api/creator/messages", json={"content": "A pantry list for rice and tea"})
    cleared = client.simulate_post("/api/creator/reset")
    assert cleared.status_code == 200
    assert cleared.json["messages"] == []
    assert cleared.json["sketch"] == {"name": "", "summary": "", "icon": "", "color": ""}


def test_a_written_page_goes_live_when_the_agent_times_out(settings, tmp_path):
    docker = FakeDocker()

    class TimeoutHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            for child in tmp_path.iterdir():
                page = child / "app" / "index.html"
                if page.is_file() and "placeholder" in page.read_text():
                    page.write_text("<!doctype html><html><body><h1>Pulse</h1></body></html>")
            raise HermesError("timed out")

    client, _tuned = _app(settings, tmp_path, docker, TimeoutHermes(), infer=_reception)
    client.simulate_post("/api/creator/messages", json={"content": "Make a simple game"})
    made = client.simulate_post("/api/creator/make")
    app_id = made.json["id"]
    assert client.simulate_get(f"/api/apps/{app_id}/manage").json["boxReady"] is True
    client.simulate_post(f"/api/apps/{app_id}/build")
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["status"] == "live"
    assert manage.json["statusError"] in (None, "")
    assert "Pulse" in (tmp_path / app_id / "app" / "index.html").read_text()
    assert docker.removed == []
    assert client.simulate_delete(f"/api/apps/{app_id}").status_code == 204


def test_runtime_requires_a_bearer_token(settings, tmp_path):
    client, _tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes())
    denied = client.simulate_get("/api/runtime/apps")
    assert denied.status_code == 401
    allowed = client.simulate_get("/api/runtime/apps", headers=TOKEN)
    assert allowed.status_code == 200
    assert allowed.json == []


def test_studio_container_is_internal_and_the_only_live_app(settings, tmp_path):
    docker = FakeDocker()
    tuned = replace(
        settings,
        apps_root=tmp_path,
        health_timeout=0,
        health_interval=0,
        vultr_api_key=VULTR_KEY,
        hermes_port_start=29180,
    )
    create_app(tuned)
    apps(tuned).update_one(
        {"slug": "stock-watchlist"},
        {"$set": {"status": "live", "statusLabel": "Live", "labels": [{"text": "Live", "tone": "success"}]}},
    )
    ensure_studio(tuned, docker, healthy=lambda _url: True)
    assert docker.runs
    joined = " ".join(docker.runs[0])
    assert f"baze-app-{STUDIO_ID}" in joined
    assert "127.0.0.1:29180:8080" in joined
    assert "127.0.0.1:29280:8642" in joined
    assert "HERMES_DASHBOARD" not in joined
    assert "9119" not in joined
    assert joined.endswith("sh /opt/data/app/run.sh")
    script = (tmp_path / STUDIO_ID / "app" / "run.sh").read_text()
    assert "hermes gateway run" in script
    page = (tmp_path / STUDIO_ID / "app" / "index.html").read_text()
    assert 'data-baze-app="studio-invoices"' in page
    favicon = (tmp_path / STUDIO_ID / "app" / "favicon.svg").read_text()
    assert 'rx="36"' in favicon
    assert 'fill="#15803d"' in favicon
    assert 'width="46"' in favicon
    assert "M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8" in favicon
    assert "Hermes" not in page
    assert 'id="ask"' not in page
    assert "/prompt" not in page
    assert (tmp_path / STUDIO_ID / "config.yaml").read_text().count("baze-inference") == 1

    client = testing.TestClient(create_app(tuned))
    shelf = client.simulate_get("/api/apps")
    assert shelf.json["summary"] == "3 apps on your shelf · 1 live"
    labels = {
        app["slug"]: [label["text"] for label in (app.get("labels") or [])]
        for app in shelf.json["apps"] + shelf.json["shared"]
    }
    assert labels["studio-invoices"] == ["New", "Take a look", "Live"]
    assert "Live" not in labels["stock-watchlist"]
    page = client.simulate_get(f"/{STUDIO_ID}")
    assert page.status_code == 302
    assert page.headers["location"] == f"/{STUDIO_ID}/"
    followed = client.simulate_get(page.headers["location"])
    assert followed.status_code == 502
    assert "not answering" in followed.text
    assert "<app-root>" not in followed.text
    assert "Hermes" not in followed.text

    http = testing.TestClient(create_app(tuned, RuntimeServices(docker, FakeHermes(), lambda fn: fn(), healthy=lambda _url: True)))
    stopped = http.simulate_post(f"/api/apps/{STUDIO_ID}/power/stop")
    assert stopped.status_code == 200
    assert stopped.json["status"] == "stopped"
    assert stopped.json["runnable"] is True
    assert [label["text"] for label in stopped.json["labels"]] == ["New", "Take a look"]
    assert docker.stopped == [f"baze-app-{STUDIO_ID}"]
    ensure_studio(tuned, docker, healthy=lambda _url: True)
    assert len(docker.runs) == 1
    refused = http.simulate_post("/api/apps/3249dc7992f5a438aa4700f77f702d6e/power/start")
    assert refused.status_code == 409
    started = http.simulate_post(f"/api/apps/{STUDIO_ID}/power/start")
    assert started.status_code == 200
    assert started.json["status"] == "live"
    assert "Live" in [label["text"] for label in started.json["labels"]]
    assert docker.started == [f"baze-app-{STUDIO_ID}"]


def test_public_path_serves_the_container_and_says_when_it_is_off(settings, tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"served {self.path}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Server", "Hermes")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        tuned = replace(settings, apps_root=tmp_path, frontend_dist=tmp_path)
        client = testing.TestClient(create_app(tuned))
        apps(tuned).update_one(
            {"_id": WATCHLIST_ID},
            {"$set": {"status": "live", "runtime.hostPort": port, "runtime.containerName": f"baze-app-{WATCHLIST_ID}"}},
        )
        page = client.simulate_get(f"/{WATCHLIST_ID}/prices")
        assert page.status_code == 200
        assert page.text == "served /prices"
        assert page.headers.get("Server") is None
        icon = client.simulate_get(f"/{WATCHLIST_ID}/favicon.svg")
        assert icon.status_code == 200
        assert icon.headers["content-type"] == "image/svg+xml"
        assert 'fill="#334155"' in icon.text
        assert "M16 7h6v6" in icon.text
        assert "served" not in icon.text

        apps(tuned).update_one({"_id": WATCHLIST_ID}, {"$set": {"status": "stopped"}})
        off = client.simulate_get(f"/{WATCHLIST_ID}")
        assert off.status_code == 503
        assert off.text == "Stock watchlist is off."
        assert "<app-root>" not in off.text
    finally:
        server.shutdown()


def test_studio_prompt_goes_to_the_harness(settings, tmp_path):
    hermes = FakeHermes()
    client, tuned = _app(settings, tmp_path, FakeDocker(), hermes)
    apps(tuned).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "runtime.harnessPort": 29280, "runtime.apiServerKey": "studio-harness-key"}},
    )
    refused = client.simulate_post(f"/api/apps/{WATCHLIST_ID}/prompt", json={"content": "Hello"})
    assert refused.status_code == 409
    sent = client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Who is unpaid?"})
    assert sent.status_code == 200
    assert sent.json["reply"] == "Noted."
    assert hermes.calls[0]["content"] == "Who is unpaid?"
    assert hermes.calls[0]["base_url"] == "http://127.0.0.1:29280"
    assert hermes.calls[0]["api_key"] == "studio-harness-key"
    client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "And the next?"})
    assert hermes.calls[1]["session_id"] == "session-1"
    managed = client.simulate_get(f"/api/apps/{STUDIO_ID}/manage")
    assert managed.status_code == 200
    assert managed.json["name"] == "Studio Invoices"
    assert isinstance(managed.json["createdAt"], int)
    assert [turn["content"] for turn in managed.json["messages"]] == [
        "Who is unpaid?",
        "Noted.",
        "And the next?",
        "Still here.",
    ]


def test_proxy_forces_the_model_and_rejects_a_missing_token(settings):
    tuned = replace(
        settings,
        vultr_api_key=VULTR_KEY,
        vultr_base_url="https://api.vultrinference.com/v1",
        model_id="deepseek-v4.1-flash-1017",
        reasoning_effort="low",
    )
    captured = {}

    def forward(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body)
        return 200, {"Content-Type": "application/json"}, b'{"ok":true}'

    missing = proxy_request(
        method="POST",
        path="/v1/chat/completions",
        headers={},
        body=b"{}",
        settings=tuned,
        token_ok=lambda token: token == "proxy-token",
        forward=forward,
    )
    assert missing[0] == 401
    assert "url" not in captured

    status, _headers, body = proxy_request(
        method="POST",
        path="/v1/chat/completions",
        headers={"Authorization": "Bearer proxy-token"},
        body=b'{"model":"other-model","messages":[]}',
        settings=tuned,
        token_ok=lambda token: token == "proxy-token",
        forward=forward,
    )
    assert status == 200
    assert captured["headers"]["Authorization"] == f"Bearer {VULTR_KEY}"
    assert captured["body"]["model"] == "deepseek-v4.1-flash-1017"
    assert captured["body"]["reasoning_effort"] == "low"
    assert captured["url"] == "https://api.vultrinference.com/v1/chat/completions"
    assert VULTR_KEY not in body.decode()

    kept = proxy_request(
        method="POST",
        path="/v1/chat/completions",
        headers={"Authorization": "Bearer proxy-token"},
        body=b'{"model":"other","reasoning_effort":"medium","messages":[]}',
        settings=tuned,
        token_ok=lambda token: token == "proxy-token",
        forward=forward,
    )
    assert kept[0] == 200
    assert captured["body"]["reasoning_effort"] == "medium"

    models = proxy_request(
        method="GET",
        path="/v1/models",
        headers={"Authorization": "Bearer proxy-token"},
        body=b"",
        settings=tuned,
        token_ok=lambda token: token == "proxy-token",
        forward=forward,
    )
    assert models[0] == 200
    assert json.loads(models[2])["data"][0]["id"] == "deepseek-v4.1-flash-1017"
    assert captured["body"]["reasoning_effort"] == "medium"

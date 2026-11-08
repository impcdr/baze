import json
from dataclasses import replace

from falcon import testing

from baze_api.app import create_app
from baze_api.catalog import STUDIO_ID, WATCHLIST_ID
from baze_api.db import apps, messages
from baze_api.hermes import HermesError
from baze_api.provisioner import busy_progress, ensure_studio
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

    def logs(self, name):
        return "BAZE-DENY TCP to 203.0.113.10 port 443."


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
    if system.startswith("You are the supervisor"):
        return '{"entries":[],"actions":[]}'
    if system.startswith("You write build plans"):
        return "Write the pantry page\nSave it in the box"
    if "JSON object" in system:
        return '{"name":"Pantry","summary":"A list of rice and tea","icon":"lucideUtensils"}'
    return "A list for rice and tea. Press Make."


def _legacy(tuned, app_id: str) -> None:
    """Keep a creator app on the older host gate. New boxes set a profile at Make."""
    apps(tuned).update_one({"_id": app_id}, {"$unset": {"runtime.profile": "", "runtime.buildName": ""}})


def test_creating_an_app_hosts_it_and_deletion_removes_the_box(settings, tmp_path):
    settings = replace(settings, admin_code="delete-this-app")
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
    assert "You choose the box." not in talked.json["messages"][1]["content"]
    assert talked.json["recommended"] == "web"
    assert talked.json["reason"] == "A list of rice and tea. Reads the web, keeps none of your data."
    assert talked.json["sketch"] == {
        "name": "Pantry",
        "summary": "A list of rice and tea",
        "icon": "lucideUtensils",
        "color": "",
    }

    missing = client.simulate_post("/api/creator/make")
    assert missing.status_code == 400
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
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
    spoken = [turn for turn in ready.json["messages"] if turn["role"] != "progress"]
    progress = [turn for turn in ready.json["messages"] if turn["role"] == "progress"]
    assert spoken[0]["content"] == "A pantry list for rice and tea"
    assert [turn["content"] for turn in progress[:3]] == [
        "Creating the container",
        "Starting the box",
        "Opening the harness",
    ]
    assert progress[3]["content"] == "Write the pantry page"
    assert [turn["state"] for turn in progress[:3]] == ["done", "done", "done"]
    assert progress[3]["state"] == "waiting"
    assert progress[0]["createdAt"] > spoken[-1]["createdAt"]
    assert progress[-1]["createdAt"] > progress[0]["createdAt"]
    cleared = client.simulate_get("/api/creator").json
    assert cleared["messages"] == []
    assert cleared["sketch"]["name"] == ""

    built = client.simulate_post(f"/api/apps/{app_id}/build")
    assert built.status_code == 202
    assert len(hermes.calls) == 2
    assert hermes.calls[1]["content"].startswith("Reply with one JSON object")
    assert "A pantry list for rice and tea" in hermes.calls[0]["content"]
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.status_code == 200
    assert manage.json["status"] == "live"
    assert "Pantry" in manage.json["messages"][-1]["content"]
    assert "Creating the container" not in hermes.calls[0]["content"]
    assert all(turn["state"] == "done" for turn in manage.json["messages"] if turn["role"] == "progress")
    assert manage.json["record"][0]["kind"] == "created"
    assert manage.json["flow"] == {"nodes": [], "edges": []}
    assert all(step["state"] == "done" for step in manage.json["steps"] if step["id"].startswith("plan"))
    page = (tmp_path / app_id / "app" / "index.html").read_text()
    assert "Pantry" in page
    assert "placeholder" not in page
    script = (tmp_path / app_id / "app" / "run.sh").read_text()
    assert "hermes gateway run" in script
    config = (tmp_path / app_id / "config.yaml").read_text()
    assert "base_url: http://baze-inference:8001/v1" in config
    assert VULTR_KEY not in config
    runs = [" ".join(args) for args in docker.runs if args and args[0] == "run"]
    build = next(line for line in runs if f"baze-build-{app_id}" in line)
    assert ":8642" in build and ":8080" not in build
    assert "--network bridge" in build
    assert "--network baze-build" not in build and "--network baze-run" not in build
    assert "baze-inference:host-gateway" in build
    assert build.endswith("sh /opt/data/app/run.sh")
    published = next(line for line in runs if f"baze-app-{app_id}" in line)
    assert ":8080" in published and "--network bridge" in published
    assert published.endswith("python3 /opt/publish/server.py")
    assert VULTR_KEY not in build and VULTR_KEY not in published

    shelf = client.simulate_get("/api/apps")
    assert shelf.json["summary"] == "4 apps on your shelf · 1 live"
    listed = next(app for app in shelf.json["apps"] if app["id"] == app_id)
    assert listed["path"] == f"/{app_id}"
    assert listed["status"] == "live"

    removed = client.simulate_delete(f"/api/apps/{app_id}", json={"code": "delete-this-app"})
    assert removed.status_code == 204
    assert docker.removed == [f"baze-build-{app_id}", f"baze-app-{app_id}"]
    assert not (tmp_path / app_id).exists()
    missing = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert missing.status_code == 404
    studio = client.simulate_delete(f"/api/apps/{STUDIO_ID}", json={"code": "delete-this-app"})
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

    client, _tuned = _app(replace(settings, admin_code="delete-this-app"), tmp_path, docker, TimeoutHermes(), infer=_reception)
    client.simulate_post("/api/creator/messages", json={"content": "Make a simple game"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    app_id = made.json["id"]
    assert client.simulate_get(f"/api/apps/{app_id}/manage").json["boxReady"] is True
    client.simulate_post(f"/api/apps/{app_id}/build")
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["status"] == "live"
    assert manage.json["statusError"] in (None, "")
    assert "Pulse" in (tmp_path / app_id / "app" / "index.html").read_text()
    assert docker.removed == []
    assert client.simulate_delete(f"/api/apps/{app_id}", json={"code": "delete-this-app"}).status_code == 204


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
            if self.path.startswith("/board"):
                body = b"<!doctype html><html><head></head><body style=\"height:100vh\"><h1>Board</h1></body></html>"
                kind = "text/html; charset=utf-8"
            else:
                body = f"served {self.path}".encode()
                kind = "text/plain"
            self.send_response(200)
            self.send_header("Content-Type", kind)
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
        assert "baze-band" not in page.text
        assert page.headers.get("Server") is None
        board = client.simulate_get(f"/{WATCHLIST_ID}/board")
        assert board.status_code == 200
        assert 'id="baze-band"' in board.text
        assert "position:fixed" in board.text
        assert "background:transparent" in board.text
        assert "padding-top:36px" in board.text
        assert "elementFromPoint" in board.text
        assert 'id="baze-band-name"' in board.text
        assert 'id="baze-band-mark"' in board.text
        assert "textShadow" in board.text
        assert 'fill="currentColor"' in board.text
        assert "Red Hat Display" in board.text
        assert "font:800 14px" in board.text
        assert 'fill="#1a5ce6"' in board.text
        assert "made with baze" in board.text
        assert "Stock watchlist" in board.text
        assert "Vultr Fanboi" in board.text
        assert ">VF<" in board.text
        signed = client.simulate_get(
            f"/{WATCHLIST_ID}/board",
            headers={"Cookie": "baze_user=max.mustermann@example.com"},
        )
        assert "Max Mustermann" in signed.text
        assert ">MM<" in signed.text
        assert "Vultr Fanboi" not in signed.text
        assert "margin" not in board.text.split('id="baze-band"')[0]
        assert board.text.index('id="baze-band"') < board.text.index("<h1>Board</h1>")
        assert board.headers.get("content-security-policy") is None
        apps(tuned).update_one(
            {"_id": WATCHLIST_ID},
            {
                "$set": {
                    "runtime.isolated": True,
                    "supervisor.grants": [{"kind": "host", "host": "example.com", "hosts": ["example.com"]}],
                }
            },
        )
        locked = client.simulate_get(f"/{WATCHLIST_ID}/board")
        policy = locked.headers["content-security-policy"]
        assert policy.startswith("connect-src 'self'")
        assert "https://example.com" in policy
        assert "http://example.com" in policy
        assert "evil.example" not in policy
        again = board.text
        assert again.count('id="baze-band"') == 1
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
    assert hermes.calls[0]["content"].endswith("Who is unpaid?")
    assert "/v1/access" in hermes.calls[0]["content"]
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


def test_a_change_logs_its_big_tasks_in_the_chat(settings, tmp_path):
    def infer(messages):
        system = messages[0]["content"]
        if system.startswith("You list the big tasks"):
            if "typo" in messages[-1]["content"]:
                return "none"
            return "Add the unpaid filter\nShow the total"
        return "Noted."

    hermes = FakeHermes()
    client, tuned = _app(settings, tmp_path, FakeDocker(), hermes, infer=infer)
    apps(tuned).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "runtime.harnessPort": 29280, "runtime.apiServerKey": "studio-harness-key"}},
    )
    sent = client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Who is unpaid?"})
    assert sent.status_code == 200
    assert hermes.calls[0]["content"].endswith("Who is unpaid?")
    assert "/v1/access" in hermes.calls[0]["content"]
    client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Fix a typo"})
    managed = client.simulate_get(f"/api/apps/{STUDIO_ID}/manage")
    assert [turn["content"] for turn in managed.json["messages"]] == [
        "Who is unpaid?",
        "Add the unpaid filter",
        "Show the total",
        "Noted.",
        "Fix a typo",
        "Still here.",
    ]
    progress = [turn for turn in managed.json["messages"] if turn["role"] == "progress"]
    assert [turn["state"] for turn in progress] == ["done", "done"]
    assert progress[0]["createdAt"] > managed.json["messages"][0]["createdAt"]
    assert progress[-1]["createdAt"] < managed.json["messages"][3]["createdAt"]


def test_an_orphaned_task_stops_spinning(settings, tmp_path):
    client, tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes())
    apps(tuned).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "runtime.harnessPort": 29280, "runtime.apiServerKey": "studio-harness-key"}},
    )
    messages(tuned).insert_one(
        {
            "_id": "progress-stuck",
            "appId": STUDIO_ID,
            "role": "progress",
            "stepId": "work-stuck-0",
            "content": "Identify Romanian news sources",
            "state": "active",
            "createdAt": 1,
        }
    )
    def task(payload):
        return next(turn for turn in payload["messages"] if turn["stepId"] == "work-stuck-0")

    with busy_progress(STUDIO_ID):
        live = client.simulate_get(f"/api/apps/{STUDIO_ID}/manage")
    assert task(live.json)["state"] == "active"
    settled = client.simulate_get(f"/api/apps/{STUDIO_ID}/manage")
    assert task(settled.json)["state"] == "stopped"
    stored = messages(tuned).find_one({"_id": "progress-stuck"})
    assert stored["state"] == "stopped"


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


def test_chart_updates_are_checked_and_files_reach_the_prompt(settings, tmp_path):
    from baze_api.chart import apply_chart, note_created

    hermes = FakeHermes()
    client, tuned = _app(settings, tmp_path, FakeDocker(), hermes)
    app_id = STUDIO_ID
    note_created(tuned, app_id, "Studio Invoices was created.")
    note_created(tuned, app_id, "Studio Invoices was created again.")
    apply_chart(
        tuned,
        app_id,
        {
            "flow": {"nodes": [{"id": "bad id", "label": "Page", "kind": "page"}], "edges": []},
            "entries": [{"kind": "created", "summary": "The model must not rewrite birth."}],
        },
    )
    apply_chart(
        tuned,
        app_id,
        {
            "flow": {
                "nodes": [
                    {"id": "person", "label": "Person", "kind": "person"},
                    {"id": "page", "label": "Invoices", "kind": "page"},
                    {"id": "out", "label": "Install", "kind": "outside"},
                ],
                "edges": [{"from": "person", "to": "page"}, {"from": "page", "to": "out"}],
            },
            "entries": [{"kind": "containment", "summary": "An install reached outside the box."}],
        },
    )
    managed = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert [line["kind"] for line in managed.json["record"]] == ["created", "containment"]
    assert managed.json["record"][0]["summary"] == "Studio Invoices was created."
    assert [node["id"] for node in managed.json["flow"]["nodes"]] == ["person", "page", "out"]

    uploads = tmp_path / "studio-files"
    apps(tuned).update_one(
        {"_id": app_id},
        {
            "$set": {
                "status": "live",
                "runtime.harnessPort": 29280,
                "runtime.apiServerKey": "studio-harness-key",
                "runtime.dataDir": str(uploads),
            }
        },
    )
    boundary = "----baze"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="../notes.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "rice\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    uploaded = client.simulate_post(
        f"/api/apps/{app_id}/files",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert uploaded.status_code == 200
    stored = uploaded.json["files"][0]["name"]
    assert "/" not in stored
    assert (uploads / "uploads" / stored).read_text() == "rice"
    sent = client.simulate_post(
        f"/api/apps/{app_id}/prompt",
        json={"content": "Use the list", "attachments": [stored]},
    )
    assert sent.status_code == 200
    assert f"/opt/data/uploads/{stored}" in hermes.calls[0]["content"]
    assert "Do not run them." in hermes.calls[0]["content"]
    assert hermes.calls[1]["content"].startswith("Reply with one JSON object")


def _supervisor_infer(messages):
    if messages[0]["content"].startswith("You are the supervisor"):
        note = ""
        try:
            note = json.loads(messages[-1]["content"]).get("note") or ""
        except (json.JSONDecodeError, TypeError, AttributeError):
            note = ""
        if note:
            suggestion = "I suggest allowing only the finance site."
        else:
            suggestion = "I suggest allowing the finance site so the prices can load. Leave anything else closed."
        return json.dumps(
            {
                "suggestion": suggestion,
                "allow": ["query1.finance.yahoo.com", "evil.example"],
            }
        )
    return _reception(messages)


def test_supervisor_holds_an_outbound_call_until_the_person_chooses(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("baze_api.supervisor.resolve_host", lambda host: ["203.0.113.10"])
    docker = FakeDocker()

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append(
                {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
            )
            page = "<!doctype html><html><body><h1>Quotes</h1><script>fetch(\"https://query1.finance.yahoo.com/v8\")</script></body></html>"
            return page, "session-built"

    hermes = PageHermes()
    client, tuned = _app(settings, tmp_path, docker, hermes, infer=_supervisor_infer)
    client.simulate_post("/api/creator/messages", json={"content": "Track two prices"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    app_id = made.json["id"]
    _legacy(tuned, app_id)
    client.simulate_post(f"/api/apps/{app_id}/build")
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["status"] == "attention"
    assert manage.json["actions"] == []
    assert manage.json["request"] == [{"host": "query1.finance.yahoo.com", "why": ""}]
    assert manage.json["sites"] == [{"host": "query1.finance.yahoo.com", "suggested": True}]
    assert all("evil.example" not in line["summary"] for line in manage.json["record"])
    notes = [turn for turn in manage.json["messages"] if turn["role"] == "supervisor"]
    assert notes[-1]["content"].startswith("I suggest allowing the finance site")
    blocked = client.simulate_get(f"/{app_id}/")
    assert blocked.status_code == 503
    assert "not deployed" in blocked.text
    before = len(hermes.calls)
    chosen = client.simulate_post(
        f"/api/apps/{app_id}/decisions",
        json={"hosts": ["query1.finance.yahoo.com"]},
    )
    assert chosen.status_code == 200
    assert len(hermes.calls) > before
    assert "query1.finance.yahoo.com" in hermes.calls[before]["content"]
    assert "supervisor" not in hermes.calls[before]["content"].lower()
    again = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert again.json["status"] == "live"
    assert again.json["request"] == []
    assert again.json["allowed"] == ["query1.finance.yahoo.com"]
    assert any("You allowed query1.finance.yahoo.com." in turn["content"] for turn in again.json["messages"] if turn["role"] == "supervisor")
    decided = next(turn for turn in again.json["messages"] if turn.get("decided"))
    assert "Allowed\nquery1.finance.yahoo.com" in decided["decision"]
    logged = next(line for line in again.json["record"] if line["kind"] == "decision")
    assert logged["summary"] == "Allowed query1.finance.yahoo.com"
    assert "query1.finance.yahoo.com" in logged["detail"]
    assert any(line["summary"] == "supervisor approved, app deployed." for line in again.json["record"])
    stored = apps(tuned).find_one({"_id": app_id})
    assert stored["runtime"].get("released") is not True
    assert stored["runtime"].get("cleared") is True
    assert stored["supervisor"]["grants"][0]["host"] == "query1.finance.yahoo.com"
    assert stored["supervisor"]["grants"][0]["addresses"]["query1.finance.yahoo.com"] == ["203.0.113.10"]
    page = tmp_path / app_id / "app" / "index.html"
    page.write_text(page.read_text() + "\nfetch(\"https://api.gdeltproject.org/api/v2/doc/doc\")\n")
    client.simulate_post(f"/api/apps/{app_id}/prompt", json={"content": "Use Bucharest news"})
    held = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert held.json["status"] == "attention"
    assert held.json["request"] == [{"host": "api.gdeltproject.org", "why": ""}]
    assert held.json["sites"] == [{"host": "api.gdeltproject.org", "suggested": False}]
    blocked_again = client.simulate_get(f"/{app_id}/")
    assert blocked_again.status_code == 503
    assert "not deployed" in blocked_again.text
    reopened = apps(tuned).find_one({"_id": app_id})
    assert reopened["runtime"].get("cleared") is not True


def test_plan_tasks_return_after_the_decision_when_the_agent_resumes(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("baze_api.supervisor.resolve_host", lambda host: ["203.0.113.10"])
    docker = FakeDocker()
    box: dict = {}

    class GateHermes(FakeHermes):
        def __init__(self):
            super().__init__()
            self.asked = False

        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append(
                {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
            )
            if self.asked or "Continue." in content:
                if "Continue." in content and self.client is not None:
                    mid = self.client.simulate_get(f"/api/apps/{box['id']}/manage").json
                    assert mid["status"] == "building"
                    assert mid["statusLabel"] == "Being made"
                    assert mid["sites"] == []
                    assert mid["working"] is True
                    assert any(
                        turn["content"] == "Write the pantry page" and turn["state"] == "active"
                        for turn in mid["messages"]
                        if turn["role"] == "progress"
                    )
                    assert all(line["summary"] != "supervisor approved, app deployed." for line in mid["record"])
                page = "<!doctype html><html><body><h1>LED</h1></body></html>"
                return page, "session-built"
            self.asked = True
            from baze_api.supervisor import submit_access

            submit_access(tuned, box["id"], [{"host": "news.google.com"}], infer=_supervisor_infer)
            return "Access request sent. Waiting before building.", "session-built"

    hermes = GateHermes()
    hermes.client = None
    client, tuned = _app(settings, tmp_path, docker, hermes, infer=_supervisor_infer)
    hermes.client = client
    client.simulate_post("/api/creator/messages", json={"content": "Top 3 LED news"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    box["id"] = made.json["id"]
    _legacy(tuned, box["id"])
    client.simulate_post(f"/api/apps/{box['id']}/build")
    held = client.simulate_get(f"/api/apps/{box['id']}/manage")
    assert held.json["status"] == "attention"
    assert held.json["statusLabel"] == "Needs a decision"
    assert held.json["sites"]
    refreshed = client.simulate_get(f"/api/apps/{box['id']}/manage")
    assert refreshed.json["status"] == "attention"
    assert refreshed.json["statusLabel"] == "Needs a decision"
    assert refreshed.json["sites"] == held.json["sites"]
    assert [turn["content"] for turn in held.json["messages"] if turn["role"] == "progress"] == [
        "Creating the container",
        "Starting the box",
        "Opening the harness",
    ]
    chosen = client.simulate_post(
        f"/api/apps/{box['id']}/decisions",
        json={"hosts": ["news.google.com"]},
    )
    assert chosen.status_code == 200
    again = client.simulate_get(f"/api/apps/{box['id']}/manage")
    allowed_at = next(
        turn["createdAt"]
        for turn in again.json["messages"]
        if turn["role"] == "supervisor" and turn["content"].startswith("You allowed")
    )
    plan = [
        turn
        for turn in again.json["messages"]
        if turn["role"] == "progress" and turn["content"] in {"Write the pantry page", "Save it in the box"}
    ]
    assert [turn["content"] for turn in plan] == ["Write the pantry page", "Save it in the box"]
    assert all(turn["createdAt"] > allowed_at and turn["state"] == "done" for turn in plan)
    reply = next(turn for turn in again.json["messages"] if turn["role"] == "assistant" and "LED" in turn["content"])
    assert reply["createdAt"] > plan[-1]["createdAt"]


def test_a_reply_reaches_the_supervisor_not_the_builder(settings, tmp_path):
    docker = FakeDocker()
    seen = []

    def infer(messages):
        seen.append(messages)
        return _supervisor_infer(messages)

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append(
                {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
            )
            page = "<!doctype html><html><body><h1>Quotes</h1><script>fetch(\"https://query1.finance.yahoo.com/v8\")</script></body></html>"
            return page, "session-built"

    hermes = PageHermes()
    client, _tuned = _app(settings, tmp_path, docker, hermes, infer=infer)
    client.simulate_post("/api/creator/messages", json={"content": "Track two prices"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    app_id = made.json["id"]
    _legacy(_tuned, app_id)
    client.simulate_post(f"/api/apps/{app_id}/build")
    before = len(hermes.calls)
    sent = client.simulate_post(
        f"/api/apps/{app_id}/prompt",
        json={"content": "Only the finance site", "to": "supervisor"},
    )
    assert sent.status_code == 200
    assert len(hermes.calls) == before
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["status"] == "attention"
    notes = [turn["content"] for turn in manage.json["messages"] if turn["role"] == "supervisor"]
    assert notes[-1] == "I suggest allowing only the finance site."
    assert manage.json["sites"] == [{"host": "query1.finance.yahoo.com", "suggested": True}]
    payload = json.loads(seen[-1][-1]["content"])
    assert payload == {"hosts": ["query1.finance.yahoo.com"], "note": "Only the finance site"}
    assert "fetch" not in json.dumps(seen[-1])


def test_the_chat_can_allow_the_suggested_sites_or_change_the_app(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("baze_api.supervisor.resolve_host", lambda host: ["203.0.113.10"])
    docker = FakeDocker()

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append(
                {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
            )
            if '"allowed"' in content:
                assert apps(self.tuned).find_one({"runtime.working": True}) is not None
                self.saw_working = True
            page = "<!doctype html><html><body><h1>Quotes</h1><script>fetch(\"https://query1.finance.yahoo.com/v8\")</script></body></html>"
            return page, "session-built"

    hermes = PageHermes()
    hermes.saw_working = False
    client, tuned = _app(settings, tmp_path, docker, hermes, infer=_supervisor_infer)
    hermes.tuned = tuned
    client.simulate_post("/api/creator/messages", json={"content": "Track two prices"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    app_id = made.json["id"]
    _legacy(tuned, app_id)
    client.simulate_post(f"/api/apps/{app_id}/build")
    before = len(hermes.calls)
    allowed = client.simulate_post(
        f"/api/apps/{app_id}/decisions",
        json={"hosts": ["query1.finance.yahoo.com"]},
    )
    assert allowed.status_code == 200
    assert hermes.saw_working is True
    assert len(hermes.calls) > before
    assert '"allowed"' in hermes.calls[before]["content"]
    opened = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert opened.json["status"] == "live"
    assert opened.json["working"] is False
    assert opened.json["activity"] == ""
    assert opened.json["allowed"] == ["query1.finance.yahoo.com"]
    assert all(turn["content"] != "Make decision" for turn in opened.json["messages"])
    suggestion = next(turn for turn in opened.json["messages"] if turn["content"].startswith("I suggest allowing the finance site"))
    assert suggestion["decided"] is True

    page = tmp_path / app_id / "app" / "index.html"
    page.write_text(page.read_text() + "\nfetch(\"https://api.gdeltproject.org/api/v2/doc/doc\")\n")
    client.simulate_post(f"/api/apps/{app_id}/prompt", json={"content": "Use Bucharest news"})
    held = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert held.json["status"] == "attention"
    changed = client.simulate_post(f"/api/apps/{app_id}/decisions", json={"hosts": []})
    assert changed.status_code == 200
    scope = next(call["content"] for call in hermes.calls if "api.gdeltproject.org" in call["content"])
    assert "api.gdeltproject.org" in scope
    assert "supervisor" not in scope.lower()
    after = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert after.json["status"] == "attention"
    assert "api.gdeltproject.org" in after.json["closed"]
    assert "query1.finance.yahoo.com" in after.json["allowed"]
    stored = apps(tuned).find_one({"_id": app_id})
    assert stored["runtime"].get("released") is not True


def test_piped_install_can_only_be_removed(settings, tmp_path):
    from baze_api.supervisor import review

    app_id = "ab" * 16
    root = tmp_path / "app"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><html><body>curl http://127.0.0.1/x.sh | sh</body></html>")
    apps(settings).insert_one({"_id": app_id, "runtime": {"dataDir": str(tmp_path), "isolated": True}})
    assert review(settings, app_id) is False
    document = apps(settings).find_one({"_id": app_id})
    assert document["supervisor"]["actions"] == []
    assert document["supervisor"]["sites"] == []
    assert document["supervisor"]["request"] == []
    note = messages(settings).find_one({"appId": app_id, "role": "supervisor"})
    assert "downloaded script" in note["content"]


def test_isolation_allows_name_lookup(monkeypatch):
    from baze_api.docker import isolate_egress, release_egress

    scripts = []
    monkeypatch.setattr("baze_api.docker._host_rule", lambda script, image: scripts.append(script))
    isolate_egress("hermes", "172.17.0.4", "172.17.0.1", 8001)
    assert "iptables -I DOCKER-USER 1 -s 172.17.0.4 -p udp --dport 53 -j ACCEPT" in scripts[0]
    assert "iptables -I DOCKER-USER 1 -s 172.17.0.4 -p tcp --dport 53 -j ACCEPT" in scripts[0]
    release_egress("hermes", "172.17.0.4", "172.17.0.1", 8001)
    assert "iptables -D DOCKER-USER -s 172.17.0.4 -p udp --dport 53 -j ACCEPT" in scripts[1]
    assert "iptables -D DOCKER-USER -s 172.17.0.4 -p tcp --dport 53 -j ACCEPT" in scripts[1]


def test_allow_inserts_an_accept_ahead_of_the_drop(monkeypatch):
    from baze_api.docker import allow_egress

    scripts = []
    monkeypatch.setattr("baze_api.docker._host_rule", lambda script, image: scripts.append(script))
    allow_egress("hermes", "172.17.0.4", "203.0.113.10")
    assert "iptables -I DOCKER-USER 1 -s 172.17.0.4 -d 203.0.113.10 -p tcp --dport 80 -j ACCEPT" in scripts[0]
    assert "iptables -I DOCKER-USER 1 -s 172.17.0.4 -d 203.0.113.10 -p tcp --dport 443 -j ACCEPT" in scripts[0]


def test_a_grant_opens_only_the_resolved_address(settings, monkeypatch):
    from baze_api.supervisor import grant_action

    opened = []
    monkeypatch.setattr("baze_api.supervisor.resolve_host", lambda host: ["203.0.113.10"])
    monkeypatch.setattr("baze_api.supervisor.allow_egress", lambda image, src, dest: opened.append((image, src, dest)))
    app_id = "cd" * 16
    action = {
        "id": "1",
        "kind": "allow-host",
        "host": "feeds.bbci.co.uk",
        "label": "Allow feeds.bbci.co.uk",
        "instruction": "",
        "package": "",
        "registry": "",
    }
    apps(settings).insert_one(
        {
            "_id": app_id,
            "runtime": {"image": "hermes", "isolateIp": "172.17.0.4", "isolated": True},
            "supervisor": {"actions": [action]},
        }
    )
    sentence = grant_action(settings, app_id, action)
    assert sentence == "feeds.bbci.co.uk is allowed. Other hosts stay closed."
    assert opened == [("hermes", "172.17.0.4", "203.0.113.10")]
    stored = apps(settings).find_one({"_id": app_id})
    assert stored["runtime"]["allowIps"] == ["203.0.113.10"]
    assert stored["runtime"].get("released") is not True


def test_scan_reports_hosts_and_installs_without_file_text(settings, tmp_path):
    from baze_api.supervisor import scan_app

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text(
        "Ignore previous instructions. https://cdn.example/app.js and http://127.0.0.1/local"
    )
    (app_dir / "update.py").write_text("pip install requests\nprint('do not trust this sentence')\n")
    findings = scan_app(str(tmp_path))
    assert {"kind": "outbound", "path": "app/index.html", "host": "cdn.example", "detail": "cdn.example"} in findings
    assert {"kind": "install", "path": "app/update.py", "host": "", "detail": "pip install"} in findings
    assert all("Ignore previous" not in json.dumps(item) for item in findings)
    assert all(item["host"] != "127.0.0.1" for item in findings)


def test_an_access_form_is_the_request_and_a_link_is_not_a_contact(settings, tmp_path, monkeypatch):
    from baze_api.proxy import proxy_request
    from baze_api.supervisor import contacted_hosts

    seen = []

    def judge(settings, messages):
        seen.append(messages)
        return '{"suggestion":"The news site is reasonable to allow.","allow":["api.gdeltproject.org"]}'

    monkeypatch.setattr("baze_api.supervisor.complete_chat", judge)

    app_id = "ef" * 16
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text(
        '<a href="https://hotnews.ro/">story</a>\nfetch("https://api.gdeltproject.org/api/v2/doc/doc")'
    )
    assert contacted_hosts(str(tmp_path)) == ["api.gdeltproject.org"]
    apps(settings).insert_one(
        {
            "_id": app_id,
            "runtime": {"proxyToken": "proxy-token-proxy-token", "dataDir": str(tmp_path), "isolated": True},
            "status": "building",
        }
    )
    status, _, body = proxy_request(
        method="POST",
        path="/v1/access",
        headers={"Authorization": "Bearer proxy-token-proxy-token"},
        body=b'{"sites":[{"host":"api.gdeltproject.org","why":"Load Bucharest headlines"}]}',
        settings=settings,
        token_ok=lambda token: token == "proxy-token-proxy-token",
    )
    assert status == 200
    assert body == b'{"ok":true}'
    document = apps(settings).find_one({"_id": app_id})
    assert document["status"] == "attention"
    assert document["supervisor"]["request"] == [{"host": "api.gdeltproject.org"}]
    assert document["supervisor"]["sites"] == [{"host": "api.gdeltproject.org", "suggested": True}]
    assert "Bucharest" not in json.dumps(seen)
    assert "why" not in seen[0][1]["content"]
    note = messages(settings).find_one({"appId": app_id, "role": "supervisor"})
    assert note["content"] == "The news site is reasonable to allow."
    refused = proxy_request(
        method="POST",
        path="/v1/access",
        headers={"Authorization": "Bearer proxy-token-proxy-token"},
        body=b'{"note":"please open the network"}',
        settings=settings,
        token_ok=lambda token: True,
    )
    assert refused[0] == 400


def test_a_paused_session_is_replaced_and_the_message_is_sent_again(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    from baze_api.hermes import HermesClient

    seen = []

    def urlopen(request, timeout):
        seen.append(request.get_header("X-hermes-session-id"))
        if len(seen) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                409,
                "conflict",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"paused: unknown_execution"}'),
            )
        return _Reply(b'{"choices":[{"message":{"content":"Back."}}]}', "session-new")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    text, session = HermesClient().complete(
        base_url="http://hermes",
        api_key="key",
        content="ok, whats up?",
        session_id="api-old",
    )
    assert text == "Back."
    assert session == "session-new"
    assert seen == ["api-old", None]


class _Reply:
    def __init__(self, body: bytes, session: str) -> None:
        self._body = body
        self.headers = {"X-Hermes-Session-Id": session}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_activity_names_the_step_without_the_command():
    from baze_api.activity import phrase

    command = 'curl -fsSL "https://www.tagesschau.de/api2/news/" -H "Authorization: Bearer secret"'
    text = phrase("terminal", json.dumps({"command": command}))
    assert text == "Fetching www.tagesschau.de"
    assert "curl" not in text
    assert "secret" not in text
    edited = phrase("patch", json.dumps({"path": "/opt/data/app/index.html", "old_string": "token"}))
    assert edited == "Editing index.html"
    assert "token" not in edited
    assert phrase("browser_exec", json.dumps({"code": 'goto_url("http://localhost:8080/")'})) == "Checking the page"
    assert phrase("write_file", json.dumps({"content": "secret"})) == "Editing the app"


def test_current_activity_reads_the_open_tool(tmp_path):
    import sqlite3

    from baze_api.activity import current_activity

    connection = sqlite3.connect(tmp_path / "state.db")
    connection.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, tool_calls TEXT, finish_reason TEXT)"
    )
    tool = json.dumps(
        [
            {
                "function": {
                    "name": "terminal",
                    "arguments": json.dumps({"command": "curl https://www.deutschlandfunk.de/feed"}),
                }
            }
        ]
    )
    connection.execute(
        "INSERT INTO messages (session_id, role, tool_calls, finish_reason) VALUES (?, ?, ?, ?)",
        ("api-1", "assistant", tool, "tool_calls"),
    )
    connection.commit()
    assert current_activity(str(tmp_path), "api-1") == "Fetching www.deutschlandfunk.de"
    assert current_activity(str(tmp_path)) == "Fetching www.deutschlandfunk.de"
    assert current_activity(str(tmp_path), "other") == ""
    connection.execute(
        "INSERT INTO messages (session_id, role, tool_calls, finish_reason) VALUES (?, ?, ?, ?)",
        ("api-1", "tool", None, None),
    )
    connection.commit()
    assert current_activity(str(tmp_path)) == "Thinking"
    connection.execute(
        "INSERT INTO messages (session_id, role, tool_calls, finish_reason) VALUES (?, ?, ?, ?)",
        ("api-1", "assistant", None, "stop"),
    )
    connection.commit()
    connection.close()
    assert current_activity(str(tmp_path)) == ""


def test_a_refresh_does_not_stop_a_live_turn(settings):
    from baze_api.activity import mark_idle, mark_working
    from baze_api.provisioner import stop_idle_progress

    app_id = "ef" * 16
    apps(settings).insert_one({"_id": app_id, "kind": "runtime", "runtime": {}})
    messages(settings).insert_one(
        {
            "_id": "m-plan",
            "appId": app_id,
            "role": "progress",
            "stepId": "plan-1",
            "state": "active",
            "content": "Write it",
            "createdAt": 1,
        }
    )
    mark_working(settings, app_id)
    stop_idle_progress(settings, app_id)
    assert messages(settings).find_one({"_id": "m-plan"})["state"] == "active"
    assert apps(settings).find_one({"_id": app_id})["runtime"]["working"] is True
    mark_idle(settings, app_id)
    stop_idle_progress(settings, app_id)
    assert messages(settings).find_one({"_id": "m-plan"})["state"] == "stopped"
    assert apps(settings).find_one({"_id": app_id})["runtime"]["working"] is False


def test_a_dropped_resume_does_not_deploy(settings, tmp_path):
    from baze_api.product import AppDecision

    app_id = "cd" * 16
    document = {
        "_id": app_id,
        "kind": "runtime",
        "status": "attention",
        "runtime": {"harnessPort": 19184, "apiServerKey": "key", "dataDir": str(tmp_path), "isolated": True},
        "build": {"steps": [{"id": "plan-1", "label": "Write the page", "state": "waiting"}]},
        "supervisor": {"released": False},
        "chat": {},
    }
    apps(settings).insert_one(document)

    class Boom(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            raise HermesError("dropped")

    services = RuntimeServices(FakeDocker(), Boom(), lambda fn: fn())
    AppDecision(settings, services)._run(document, 19184, "key", ["news.google.com"], [], 1)
    stored = apps(settings).find_one({"_id": app_id})
    assert stored["runtime"]["working"] is False
    assert stored["status"] == "attention"
    assert stored["statusLabel"] == "Not deployed"
    record = (stored.get("chart") or {}).get("record") or []
    assert all(item.get("summary") != "supervisor approved, app deployed." for item in record)
    turn = messages(settings).find_one({"appId": app_id, "role": "progress"})
    assert turn["content"] == "Write the page"
    assert turn["state"] == "stopped"


def test_a_refresh_during_creation_does_not_stop_the_tasks(settings):
    from baze_api.provisioner import stop_idle_progress

    app_id = "aa" * 16
    apps(settings).insert_one({"_id": app_id, "kind": "runtime", "status": "building", "runtime": {}})
    messages(settings).insert_one(
        {
            "_id": "m-build",
            "appId": app_id,
            "role": "progress",
            "stepId": "plan-1",
            "state": "active",
            "content": "Write the page",
            "createdAt": 1,
        }
    )
    stop_idle_progress(settings, app_id)
    assert messages(settings).find_one({"_id": "m-build"})["state"] == "active"


def test_a_stopped_plan_is_not_deployed(settings, tmp_path):
    from baze_api.provisioner import _finish_build

    app_id = "bb" * 16
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.html").write_text("<!doctype html><html><body>Hi</body></html>")
    apps(settings).insert_one(
        {
            "_id": app_id,
            "status": "building",
            "runtime": {"isolated": True, "dataDir": str(tmp_path), "hostPort": 9},
            "build": {"steps": [{"id": "plan-1", "label": "Write the page", "state": "stopped"}]},
            "supervisor": {},
            "chart": {"record": []},
        }
    )
    messages(settings).insert_one(
        {
            "_id": "m-stopped",
            "appId": app_id,
            "role": "progress",
            "stepId": "plan-1",
            "state": "stopped",
            "content": "Write the page",
            "createdAt": 1,
        }
    )
    _finish_build(settings, app_id, FakeDocker(), None)
    stored = apps(settings).find_one({"_id": app_id})
    assert stored["status"] == "attention"
    assert stored["statusLabel"] == "Not deployed"
    assert messages(settings).find_one({"_id": "m-stopped"})["state"] == "stopped"
    assert all(item.get("summary") != "supervisor approved, app deployed." for item in (stored.get("chart") or {}).get("record") or [])


def test_creation_does_not_deploy_while_the_turn_is_still_running(settings, tmp_path):
    docker = FakeDocker()

    class SlowHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append(
                {"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id}
            )
            if content.startswith("Reply with one JSON"):
                return "Noted.", session_id or "session-built"
            html = "<!doctype html><html><body><h1>Pantry</h1></body></html>"
            (tmp_path / self.app_id / "app" / "index.html").write_text(html)
            self.mid = self.client.simulate_get(f"/api/apps/{self.app_id}/manage").json
            return html, "session-built"

    hermes = SlowHermes()
    client, _tuned = _app(settings, tmp_path, docker, hermes, infer=_reception)
    hermes.client = client
    client.simulate_post("/api/creator/messages", json={"content": "A pantry list for rice and tea"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    hermes.app_id = made.json["id"]
    built = client.simulate_post(f"/api/apps/{hermes.app_id}/build")
    assert built.status_code == 202
    mid = hermes.mid
    assert mid["status"] == "building"
    assert mid["working"] is True
    assert mid["statusLabel"] != "Needs a decision"
    assert all(line["summary"] != "supervisor approved, app deployed." for line in mid["record"])
    assert any(
        turn["content"] == "Write the pantry page" and turn["state"] == "active"
        for turn in mid["messages"]
        if turn["role"] == "progress"
    )
    assert all(turn["state"] != "stopped" for turn in mid["messages"] if turn["role"] == "progress")
    done = client.simulate_get(f"/api/apps/{hermes.app_id}/manage")
    assert done.json["status"] == "live"
    assert done.json["working"] is False
    assert done.json["statusLabel"] == "Live"
    assert all(turn["state"] == "done" for turn in done.json["messages"] if turn["role"] == "progress")
    assert any(line["summary"] == "supervisor approved, app deployed." for line in done.json["record"])


def test_hosted_room_follows_memory_and_running_demos():
    from baze_api.limits import hosted_room

    assert hosted_room(7935, 768, 4) == 2
    assert hosted_room(16000, 512, 1) == (16000 * 3) // (512 * 5) - 1
    assert hosted_room(512, 512, 9) == 0


def test_a_third_temporary_app_is_refused(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("baze_api.limits.mem_total_mb", lambda: 1707)
    monkeypatch.setattr("baze_api.limits.running_demo_count", lambda _settings: 0)
    client, tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes(), infer=_reception)
    from baze_api.limits import temporary_room

    assert temporary_room(tuned) == 2
    visitor = {"remote_addr": "203.0.113.10"}
    for _ in range(2):
        talked = client.simulate_post("/api/creator/messages", json={"content": "A pantry list"}, **visitor)
        assert talked.status_code == 200
        made = client.simulate_post("/api/creator/make", json={"profile": "web"}, **visitor)
        assert made.status_code == 201
        stored = apps(tuned).find_one({"_id": made.json["id"]})
        assert stored["demo"] is False
        assert stored["expiresAt"] > stored["createdAt"]
    client.simulate_post("/api/creator/messages", json={"content": "Another pantry list"}, **visitor)
    refused = client.simulate_post("/api/creator/make", json={"profile": "web"}, **visitor)
    assert refused.status_code == 429
    assert refused.json["description"] == "This machine can host 2 temporary apps at once, and that many are already running."
    assert apps(tuned).count_documents({"demo": False}) == 2


def test_a_third_overlapping_turn_is_refused(settings, tmp_path):
    from baze_api.limits import begin_start, release_turn

    client, tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes())
    apps(tuned).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "runtime.harnessPort": 29280, "runtime.apiServerKey": "studio-harness-key"}},
    )
    begin_start(tuned, "127.0.0.1")
    begin_start(tuned, "127.0.0.1")
    refused = client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Who is unpaid?"})
    assert refused.status_code == 429
    assert "being built" in refused.json["description"]
    release_turn()
    release_turn()
    sent = client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Who is unpaid?"})
    assert sent.status_code == 200


def test_the_fifth_start_from_one_visitor_is_refused(settings, tmp_path):
    from baze_api.limits import begin_start, release_turn

    client, tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes())
    apps(tuned).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "runtime.harnessPort": 29280, "runtime.apiServerKey": "studio-harness-key"}},
    )
    visitor = {"remote_addr": "203.0.113.20"}
    for _ in range(4):
        begin_start(tuned, "203.0.113.20")
        release_turn()
    refused = client.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Again"}, **visitor)
    assert refused.status_code == 429
    assert refused.json["description"] == "This visitor has started enough apps for now. Try again later."
    other = client.simulate_post(
        f"/api/apps/{STUDIO_ID}/prompt",
        json={"content": "From elsewhere"},
        remote_addr="203.0.113.21",
    )
    assert other.status_code == 200


def test_reads_stay_open_when_starts_are_used_up(settings, tmp_path):
    from baze_api.limits import begin_start, release_turn

    client, tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes())
    visitor = {"remote_addr": "203.0.113.30"}
    for _ in range(4):
        begin_start(tuned, "203.0.113.30")
        release_turn()
    assert client.simulate_get("/api/health", **visitor).status_code == 200
    assert client.simulate_get("/api/account", **visitor).status_code == 200
    assert client.simulate_get(f"/api/apps/{STUDIO_ID}/manage", **visitor).status_code == 200


def test_the_proxy_stops_once_the_daily_count_is_reached(settings, monkeypatch):
    from baze_api.proxy import InferenceError, complete_chat

    tuned = replace(settings, vultr_api_key=VULTR_KEY, model_calls_per_day=1)
    forwarded = []

    def forward(url, headers, body):
        forwarded.append(url)
        return 200, {"Content-Type": "application/json"}, b'{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr("baze_api.proxy._forward", forward)
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
    assert forwarded == []
    first = proxy_request(
        method="POST",
        path="/v1/chat/completions",
        headers={"Authorization": "Bearer proxy-token"},
        body=b'{"messages":[]}',
        settings=tuned,
        token_ok=lambda token: token == "proxy-token",
        forward=forward,
    )
    assert first[0] == 200
    assert len(forwarded) == 1
    blocked = proxy_request(
        method="POST",
        path="/v1/chat/completions",
        headers={"Authorization": "Bearer proxy-token"},
        body=b'{"messages":[]}',
        settings=tuned,
        token_ok=lambda token: token == "proxy-token",
        forward=forward,
    )
    assert blocked[0] == 429
    assert len(forwarded) == 1
    try:
        complete_chat(tuned, [{"role": "user", "content": "hi"}])
    except InferenceError as exc:
        assert "enough for today" in str(exc)
    else:
        raise AssertionError("complete_chat forwarded after the daily count")
    assert len(forwarded) == 1


def test_a_temporary_app_expires_and_a_demo_app_stays(settings, tmp_path):
    from baze_api.limits import expire_temporary
    from baze_api.provisioner import busy_progress

    tuned = replace(settings, apps_root=tmp_path)
    docker = FakeDocker()
    temporary = "ab" * 16
    demo = "cd" * 16
    temporary_dir = tmp_path / temporary
    temporary_dir.mkdir()
    demo_dir = tmp_path / demo
    demo_dir.mkdir()
    apps(tuned).insert_one(
        {
            "_id": temporary,
            "slug": "temporary-hour",
            "demo": False,
            "status": "live",
            "expiresAt": 1,
            "runtime": {"containerName": f"baze-app-{temporary}", "dataDir": str(temporary_dir)},
        }
    )
    apps(tuned).insert_one(
        {
            "_id": demo,
            "slug": "demo-stays",
            "demo": True,
            "status": "live",
            "expiresAt": 1,
            "runtime": {"containerName": f"baze-app-{demo}", "dataDir": str(demo_dir)},
        }
    )
    with busy_progress(temporary):
        assert expire_temporary(tuned, docker) == 0
        assert apps(tuned).find_one({"_id": temporary}) is not None
    assert expire_temporary(tuned, docker) == 1
    assert apps(tuned).find_one({"_id": temporary}) is None
    assert not temporary_dir.exists()
    assert docker.removed == [f"baze-app-{temporary}"]
    assert apps(tuned).find_one({"_id": demo}) is not None
    assert demo_dir.exists()


def test_the_admin_code_deletes_an_app(settings, tmp_path):
    tuned = replace(settings, admin_code="delete-this-app", apps_root=tmp_path)
    client, tuned = _app(tuned, tmp_path, FakeDocker(), FakeHermes(), infer=_reception)
    talked = client.simulate_post("/api/creator/messages", json={"content": "A pantry list"})
    assert talked.status_code == 200
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    assert made.status_code == 201
    app_id = made.json["id"]
    wrong = client.simulate_delete(f"/api/apps/{app_id}", json={"code": "nope"})
    assert wrong.status_code == 403
    assert wrong.json["description"] == "That code does not delete this app"
    assert "nope" not in wrong.text
    assert client.simulate_get(f"/api/apps/{app_id}/manage").status_code == 200
    shared = client.simulate_post(
        f"/api/apps/{app_id}/share",
        json={"email": "max.mustermann@example.com", "shared": True},
    )
    assert shared.status_code == 200
    stranger = client.simulate_delete(
        f"/api/apps/{app_id}",
        json={"code": "delete-this-app"},
        headers={"Cookie": "baze_user=max.mustermann@example.com"},
    )
    assert stranger.status_code == 403
    assert stranger.json["description"] == "You can use this app. You can't change it."
    assert client.simulate_get(f"/api/apps/{app_id}/manage").status_code == 200
    removed = client.simulate_delete(f"/api/apps/{app_id}", json={"code": "delete-this-app"})
    assert removed.status_code == 204
    assert client.simulate_get(f"/api/apps/{app_id}/manage").status_code == 404


def test_the_admin_code_persists_a_temporary_app(settings, tmp_path):
    tuned = replace(settings, admin_code="persist-this-app", apps_root=tmp_path)
    client, tuned = _app(tuned, tmp_path, FakeDocker(), FakeHermes(), infer=_reception)
    talked = client.simulate_post("/api/creator/messages", json={"content": "A pantry list"})
    assert talked.status_code == 200
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    assert made.status_code == 201
    app_id = made.json["id"]
    page = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert page.json["demo"] is False
    assert isinstance(page.json["expiresAt"], int)
    wrong = client.simulate_post(f"/api/apps/{app_id}/persist", json={"code": "nope"})
    assert wrong.status_code == 403
    assert wrong.json["description"] == "That code does not persist this app"
    assert "nope" not in wrong.text
    shared = client.simulate_post(
        f"/api/apps/{app_id}/share",
        json={"email": "max.mustermann@example.com", "shared": True},
    )
    assert shared.status_code == 200
    stranger = client.simulate_post(
        f"/api/apps/{app_id}/persist",
        json={"code": "persist-this-app"},
        headers={"Cookie": "baze_user=max.mustermann@example.com"},
    )
    assert stranger.status_code == 403
    assert stranger.json["description"] == "You can use this app. You can't change it."
    kept = client.simulate_post(f"/api/apps/{app_id}/persist", json={"code": "persist-this-app"})
    assert kept.status_code == 200
    assert kept.json == {"demo": True, "expiresAt": None}
    fresh = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert fresh.json["demo"] is True
    assert fresh.json["expiresAt"] is None


def test_web_egress_clears_old_rules_and_installs_none():
    from baze_api.boxes import egress_script

    script = egress_script("172.17.0.4", "web", "172.17.0.1", 8001)
    assert "iptables -D DOCKER-USER" in script
    assert r"172\.17\.0\.4[^ ]*" in script
    assert "REJECT" not in script
    assert "ACCEPT" not in script
    assert "BAZE-DENY" not in script
    closed = egress_script("172.17.0.4", "closed", "172.17.0.1", 8001)
    assert "-s 172.17.0.4 -j ACCEPT" not in closed
    assert "-d 169.254.0.0/16 -j REJECT" in closed
    assert "BAZE-DENY" in closed


def test_a_stopped_call_is_a_short_record_with_details(settings):
    from baze_api.boxes import parse_denials, record_denials
    from baze_api.chart import public_chart
    from baze_api.db import apps

    app_id = "a" * 32
    apps(settings).insert_one({"_id": app_id, "chart": {"record": []}, "runtime": {"boxIps": ["172.17.0.4"]}})
    text = (
        "BAZE-DENY IN=docker0 OUT=eth0 SRC=172.17.0.4 DST=93.184.216.34 "
        "LEN=60 PROTO=TCP SPT=40000 DPT=443 WINDOW=0"
    )
    found = parse_denials(text + "\n" + text)
    assert found == [("172.17.0.4", "93.184.216.34", "TCP", "443")]
    record_denials(settings, found)
    record_denials(settings, found)
    _, record = public_chart(apps(settings).find_one({"_id": app_id}))
    assert len(record) == 1
    assert record[0]["kind"] == "containment"
    assert record[0]["summary"] == "A call was stopped."
    assert record[0]["detail"] == "TCP to 93.184.216.34 port 443."


def test_a_web_box_does_not_pause_for_a_public_site(settings, tmp_path):
    docker = FakeDocker()

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append({"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id})
            page = '<!doctype html><html><body><h1>News</h1><script>fetch("https://news.google.com/rss")</script></body></html>'
            return page, "session-built"

    hermes = PageHermes()
    client, _tuned = _app(settings, tmp_path, docker, hermes, infer=_reception)
    client.simulate_post("/api/creator/messages", json={"content": "A news page"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    app_id = made.json["id"]
    client.simulate_post(f"/api/apps/{app_id}/build")
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["status"] == "live"
    assert manage.json["box"]["name"] == "Web box"
    assert manage.json["sites"] == []
    joined = "\n".join(call["content"] for call in hermes.calls)
    assert "This is a Web box." not in joined
    assert "The page may call public sites." not in joined
    assert "Do not stop to ask for an ordinary public website." not in joined
    assert "Two short sentences about what the app does." in joined
    from baze_api.app_proxy import connect_policy
    from baze_api.db import apps

    assert connect_policy(apps(settings).find_one({"_id": app_id})) is None


def test_a_starter_flag_does_not_block_the_app_and_the_path_opens_with_the_box(settings, tmp_path):
    from baze_api.app_proxy import _page_origin
    from baze_api.db import apps

    class QuietHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append({"content": content})
            return "Three prices on one screen. They refresh on their own.", "session-built"

    client, _tuned = _app(settings, tmp_path, FakeDocker(), QuietHermes(), infer=_reception)
    client.simulate_post("/api/creator/messages", json={"content": "Track three prices"})
    made = client.simulate_post("/api/creator/make", json={"profile": "web"})
    app_id = made.json["id"]
    opened = client.simulate_get(f"/{app_id}/")
    assert opened.status_code == 503
    assert "being made" in opened.text
    assert "off" not in opened.text
    client.simulate_post(f"/api/apps/{app_id}/build")
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["status"] == "live"
    assert manage.json["statusError"] in (None, "")
    assert 'data-baze-build="placeholder"' in (tmp_path / app_id / "app" / "index.html").read_text()
    document = apps(settings).find_one({"_id": app_id})
    document["status"] = "building"
    document["runtime"]["boxReady"] = True
    document["runtime"]["boxIps"] = ["172.17.0.9"]
    assert _page_origin(document) == "http://172.17.0.9:8080"


def test_a_data_box_asks_before_a_lookup_and_leaves_records_behind(settings, tmp_path):
    from baze_api.boxes import copy_code

    docker = FakeDocker()

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append({"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id})
            page = '<!doctype html><html><body><h1>Invoices</h1><script>fetch("https://example.com/lib")</script></body></html>'
            return page, session_id or "session-built"

    hermes = PageHermes()
    client, tuned = _app(settings, tmp_path, docker, hermes, infer=_reception)
    talked = client.simulate_post("/api/creator/messages", json={"content": "Invoices for the shop"})
    assert talked.json["recommended"] == "data"
    assert "Holds your data, talks only to what you approve." in talked.json["reason"]
    made = client.simulate_post("/api/creator/make", json={"profile": "data"})
    app_id = made.json["id"]
    source = tmp_path / app_id / "app"
    (source / "invoices.json").write_text('[{"who":"Ada"}]')
    client.simulate_post(f"/api/apps/{app_id}/build")
    held = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert held.json["status"] == "attention"
    assert held.json["boxPrompt"] == "This update needs to look something up."
    assert held.json["box"]["id"] == "data"
    publish = tmp_path / f"{app_id}-publish"
    assert not (publish / "invoices.json").exists()
    allowed = client.simulate_post(f"/api/apps/{app_id}/decisions", json={"allow": True})
    assert allowed.status_code == 200
    assert allowed.json["reply"] == "You allowed it."
    assert any("You allowed it." in call["content"] for call in hermes.calls)
    stored = apps(tuned).find_one({"_id": app_id})
    assert stored["runtime"]["boxAllows"] == ["lookup"]
    live = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert live.json["status"] == "live"
    dest = tmp_path / "copied"
    copy_code(source, dest)
    assert not (dest / "invoices.json").exists()


def test_a_quarantine_box_reports_and_does_not_publish_the_file(settings, tmp_path):
    docker = FakeDocker()
    seen = []

    def infer(messages):
        system = messages[0]["content"]
        if "sealed box" in system:
            return "Verify the item at /specimen. Leave it unchanged."
        if "sealed check" in system:
            seen.append(messages[1]["content"])
            return '{"verdict": "suspicious", "report": "A call was stopped."}'
        return _reception(messages)

    class PageHermes(FakeHermes):
        def complete(self, *, base_url, api_key, content, session_id):
            self.calls.append({"base_url": base_url, "api_key": api_key, "content": content, "session_id": session_id})
            return "Ran the file.", "session-built"

    hermes = PageHermes()
    client, _tuned = _app(settings, tmp_path, docker, hermes, infer=infer)
    client.simulate_post("/api/creator/messages", json={"content": "Check this file"})
    thread = client.simulate_get("/api/creator")
    assert thread.json["recommended"] == "quarantine"
    made = client.simulate_post("/api/creator/make", json={"profile": "quarantine"})
    app_id = made.json["id"]
    specimen = tmp_path / app_id / "specimen"
    specimen.mkdir(parents=True, exist_ok=True)
    (specimen / "sample.txt").write_text("do-not-leak-this-specimen")
    client.simulate_post(f"/api/apps/{app_id}/build")
    manage = client.simulate_get(f"/api/apps/{app_id}/manage")
    assert manage.json["check"] is True
    assert manage.json["status"] == "closed"
    assert manage.json["canPrompt"] is False
    assert manage.json["box"]["name"] == "Quarantine box"
    notes = [turn["content"] for turn in manage.json["messages"] if turn["role"] == "supervisor"]
    assert notes == ["A call was stopped."]
    assert all("Ran the file." not in turn["content"] for turn in manage.json["messages"])
    assert hermes.calls
    assert "/specimen" in hermes.calls[0]["content"]
    assert "index.html" not in hermes.calls[0]["content"]
    assert seen and "BAZE-DENY" in seen[0]
    assert "do-not-leak-this-specimen" not in seen[0]
    runs = [" ".join(args) for args in docker.runs if args and args[0] == "run"]
    build = next(line for line in runs if f"baze-build-{app_id}" in line)
    assert "/specimen:ro" in build
    assert "--read-only" in build
    assert "--tmpfs /run:rw,exec,nosuid,size=64m" in build
    assert "--cap-add SETUID" in build
    assert "HERMES_UID=10000" in build
    assert "/opt/baze-access.so:ro" in build
    assert "/etc/ld.so.preload:ro" in build
    assert "--cap-drop ALL" in build
    assert "no-new-privileges" in build
    assert "--pids-limit 64" in build
    assert "--network bridge" in build
    assert ":8080" not in build
    assert not any("python3 /opt/publish/server.py" in line for line in runs)
    assert f"baze-build-{app_id}" in docker.removed
    opened = client.simulate_get(f"/{app_id}/")
    assert opened.status_code == 200
    assert "This is a check, not an app." in opened.text
    shelf = client.simulate_get("/api/apps").json
    assert all(app["id"] != app_id for app in shelf["apps"])
    check = next(item for item in shelf["checks"] if item["id"] == app_id)
    assert check["specimen"] == "sample.txt (25 bytes)"
    assert check["verdict"] == "suspicious"
    assert check["report"] == "A call was stopped."
    refused = client.simulate_post(f"/api/apps/{app_id}/prompt", json={"content": "Look again"})
    assert refused.status_code == 409
    assert refused.json["description"] == "This check is finished."


def test_the_make_choice_uses_the_context_reception_gathered(settings, tmp_path):
    from baze_api.boxes import suggestion_reason

    assert suggestion_reason("data", "Invoices for the shop") == (
        "Invoices for the shop. Holds your data, talks only to what you approve."
    )
    assert suggestion_reason("quarantine", "Check this file") == (
        "Check this file. Runs untrusted things sealed off, then reports back."
    )
    client, _tuned = _app(settings, tmp_path, FakeDocker(), FakeHermes(), infer=_reception)
    talked = client.simulate_post("/api/creator/messages", json={"content": "Invoices for the shop"})
    assert "box" not in talked.json["messages"][-1]["content"].lower()
    assert talked.json["recommended"] == "data"

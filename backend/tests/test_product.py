from falcon import testing

from baze_api.catalog import FOLLOWUPS_ID, STUDIO_ID, WATCHLIST_ID

TOKEN = {"Authorization": "Bearer test-token-test-token"}


def test_account_is_the_seeded_user_without_a_token(client):
    result = testing.TestClient(client).simulate_get("/api/account")
    assert result.status_code == 200
    assert result.json["email"] == "vultrfanboi@example.com"
    assert result.json["name"] == "Vultr Fanboi"
    assert result.json["initials"] == "VF"


def test_home_shelf_and_studio_draft_match_the_catalog(client):
    http = testing.TestClient(client)
    home = http.simulate_get("/api/home")
    assert home.status_code == 200
    assert home.json["greeting"] == "Good afternoon, Lena"
    assert home.json["seeAllLabel"] == "See all 3"
    assert [app["name"] for app in home.json["featured"]] == [
        "Studio Invoices",
        "Stock watchlist",
        "Client follow-ups",
    ]
    assert [app["path"] for app in home.json["featured"]] == [
        f"/{STUDIO_ID}",
        f"/{WATCHLIST_ID}",
        f"/{FOLLOWUPS_ID}",
    ]

    shelf = http.simulate_get("/api/apps")
    assert shelf.status_code == 200
    assert shelf.json["summary"] == "3 apps on your shelf · 0 live"
    assert all(
        label.get("text") != "Live"
        for app in shelf.json["apps"] + shelf.json["shared"]
        for label in (app.get("labels") or [])
    )
    by_slug = {app["slug"]: app for app in shelf.json["apps"]}
    assert set(by_slug) == {"studio-invoices", "stock-watchlist", "client-follow-ups"}
    assert by_slug["studio-invoices"]["path"] == f"/{STUDIO_ID}"
    assert by_slug["stock-watchlist"]["path"] == f"/{WATCHLIST_ID}"
    assert by_slug["client-follow-ups"]["path"] == f"/{FOLLOWUPS_ID}"
    assert shelf.json["shared"] == []

    draft = http.simulate_get("/api/drafts/studio")
    assert draft.status_code == 200
    assert draft.json["messages"][0]["text"].startswith("Invoices for my design studio")
    assert draft.json["ready"]["openPath"] == f"/{STUDIO_ID}"

    workspace = http.simulate_get(f"/api/apps/{STUDIO_ID}/workspace")
    assert workspace.status_code == 200
    assert workspace.json["name"] == "Studio Invoices"
    assert workspace.json["sections"][0]["panel"]["rows"] == []


def test_draft_edits_persist_and_publish_uses_the_app_id(client):
    http = testing.TestClient(client)
    patched = http.simulate_patch("/api/drafts/studio", json={"preset": "plum"})
    assert patched.status_code == 200
    assert patched.json["selectedPreset"] == "plum"
    assert patched.json["ready"]["facts"][2]["value"] == "Plum"

    posted = http.simulate_post("/api/drafts/studio/messages", json={"text": "Add Sunday"})
    assert posted.json["messages"][-1]["role"] == "baze"
    assert posted.json["messages"][-2]["text"] == "Add Sunday"

    published = http.simulate_post("/api/drafts/studio/publish", json={})
    assert published.status_code == 200
    shelf = http.simulate_get("/api/apps", query_string="status=live")
    studio = next(app for app in shelf.json["apps"] if app["slug"] == "studio-invoices")
    assert studio["status"] == "live"
    assert studio["path"] == f"/{STUDIO_ID}"

    shared = http.simulate_post("/api/drafts/studio/share", json={})
    assert shared.json["message"] == "The safety check link is ready to share."


def test_new_prompt_creates_a_draft_and_invoice_reopens_studio(client):
    http = testing.TestClient(client)
    created = http.simulate_post("/api/drafts", json={"prompt": "A quiet reading list"})
    assert created.status_code == 201
    assert created.json["id"] == "draft-2"
    assert created.json["messages"][0]["text"] == "A quiet reading list"

    again = http.simulate_post("/api/drafts", json={"prompt": "Invoices for the studio"})
    assert again.json["id"] == "studio"

    missing = http.simulate_get(f"/api/apps/{'ab' * 16}/workspace")
    assert missing.status_code == 404


def test_max_can_open_a_shared_app_but_cannot_change_it(client):
    http = testing.TestClient(client)
    account = http.simulate_get("/api/account")
    assert account.json["studio"] == "Lindner Studio"
    assert [person["name"] for person in account.json["accounts"]] == [
        "Vultr Fanboi",
        "Max Mustermann",
        "Erika Mustermann",
        "Otto Normalverbraucher",
    ]
    granted = http.simulate_post(
        f"/api/apps/{STUDIO_ID}/share",
        json={"email": "max.mustermann@example.com", "shared": True},
    )
    assert granted.status_code == 200
    max_row = next(row for row in granted.json["shares"] if row["email"] == "max.mustermann@example.com")
    assert max_row["shared"] is True
    owner = next(row for row in granted.json["shares"] if row["owner"])
    assert owner["name"] == "Vultr Fanboi"
    switched = http.simulate_post("/api/account", json={"email": "erika.mustermann@example.com"})
    assert switched.status_code == 200
    assert switched.json["name"] == "Erika Mustermann"
    switched = http.simulate_post("/api/account", json={"email": "max.mustermann@example.com"})
    assert switched.json["name"] == "Max Mustermann"
    cookie = {"Cookie": "baze_user=max.mustermann@example.com"}
    shelf = http.simulate_get("/api/apps", headers=cookie)
    assert shelf.json["apps"] == []
    assert [app["name"] for app in shelf.json["shared"]] == ["Studio Invoices"]
    assert shelf.json["shared"][0]["sharedBy"] == "Vultr Fanboi"
    assert shelf.json["shared"][0]["deletable"] is False
    assert [person["initials"] for person in shelf.json["shared"][0]["people"]] == ["VF", "MM"]
    manage = http.simulate_get(f"/api/apps/{STUDIO_ID}/manage", headers=cookie)
    assert manage.status_code == 200
    assert manage.json["canPrompt"] is False
    assert any(row["email"] == "max.mustermann@example.com" and row["shared"] for row in manage.json["shares"])
    refused = http.simulate_post(f"/api/apps/{STUDIO_ID}/prompt", json={"content": "Change the colors"}, headers=cookie)
    assert refused.status_code == 403


def test_conversations_still_require_a_bearer_token(client):
    result = testing.TestClient(client).simulate_get("/api/conversations")
    assert result.status_code == 401
    allowed = testing.TestClient(client).simulate_get("/api/conversations", headers=TOKEN)
    assert allowed.status_code == 200

from falcon import testing

from baze_api.catalog import SHIFTS_ID, STUDIO_ID

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
    assert home.json["seeAllLabel"] == "See all 6"
    assert [app["name"] for app in home.json["featured"]] == [
        "Studio Invoices",
        "Stock watchlist",
        "Stock room",
        "Café shifts",
    ]
    assert home.json["featured"][0]["path"] == f"/{STUDIO_ID}"

    shelf = http.simulate_get("/api/apps")
    assert shelf.status_code == 200
    assert shelf.json["summary"] == "6 apps on your shelf · 3 live"
    by_slug = {app["slug"]: app for app in shelf.json["apps"]}
    assert by_slug["studio-invoices"]["path"] == f"/{STUDIO_ID}"
    assert by_slug["cafe-shifts"]["path"] == "/building/shifts"
    assert [app["name"] for app in shelf.json["shared"]] == ["Holiday cover", "Menu board"]

    draft = http.simulate_get("/api/drafts/studio")
    assert draft.status_code == 200
    assert draft.json["messages"][0]["text"].startswith("Invoices for my design studio")
    assert draft.json["ready"]["openPath"] == f"/{STUDIO_ID}"

    workspace = http.simulate_get(f"/api/apps/{STUDIO_ID}/workspace")
    assert workspace.status_code == 200
    assert workspace.json["name"] == "Studio Invoices"
    assert workspace.json["sections"][0]["panel"]["rows"][0]["cells"][1] == "Nordlicht Café"


def test_draft_edits_persist_and_publish_uses_the_app_id(client):
    http = testing.TestClient(client)
    patched = http.simulate_patch("/api/drafts/shifts", json={"preset": "plum"})
    assert patched.status_code == 200
    assert patched.json["selectedPreset"] == "plum"
    assert patched.json["ready"]["facts"][2]["value"] == "Plum"

    posted = http.simulate_post("/api/drafts/shifts/messages", json={"text": "Add Sunday"})
    assert posted.json["messages"][-1]["role"] == "baze"
    assert posted.json["messages"][-2]["text"] == "Add Sunday"

    published = http.simulate_post("/api/drafts/shifts/publish", json={})
    assert published.status_code == 200
    shelf = http.simulate_get("/api/apps", query_string="status=live")
    shifts = next(app for app in shelf.json["apps"] if app["slug"] == "cafe-shifts")
    assert shifts["status"] == "live"
    assert shifts["path"] == f"/{SHIFTS_ID}"

    shared = http.simulate_post("/api/drafts/studio/share", json={})
    assert shared.json["message"] == "The safety check link is ready to share."


def test_new_prompt_creates_a_draft_and_invoice_reopens_studio(client):
    http = testing.TestClient(client)
    created = http.simulate_post("/api/drafts", json={"prompt": "A quiet reading list"})
    assert created.status_code == 201
    assert created.json["id"] == "draft-3"
    assert created.json["messages"][0]["text"] == "A quiet reading list"

    again = http.simulate_post("/api/drafts", json={"prompt": "Invoices for the studio"})
    assert again.json["id"] == "studio"

    missing = http.simulate_get(f"/api/apps/{'ab' * 16}/workspace")
    assert missing.status_code == 404


def test_conversations_still_require_a_bearer_token(client):
    result = testing.TestClient(client).simulate_get("/api/conversations")
    assert result.status_code == 401
    allowed = testing.TestClient(client).simulate_get("/api/conversations", headers=TOKEN)
    assert allowed.status_code == 200

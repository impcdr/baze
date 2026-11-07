"""Seed catalog for the signed-in user. Screens match the former in-browser mock."""

from __future__ import annotations

USER_EMAIL = "vultrfanboi@example.com"
USER_NAME = "Vultr Fanboi"
USER_INITIALS = "VF"
USER_COLOR = "#22c79b"
USER_INK = "#0b1b3f"

STUDIO_ID = "eca299ce2f7bc6d8c3f360f68683dd11"
WATCHLIST_ID = "3249dc7992f5a438aa4700f77f702d6e"
FOLLOWUPS_ID = "7e408db2ac722382fcc9fccbcc899d92"
STOCK_ID = "93703d90f9a5430b393283b7bc2e85f0"
SHIFTS_ID = "6f064f659b2d5fd5bab185463126ada7"
EXPENSES_ID = "e0d9a50eef7d7dbd4d7e8a5d10477b5f"
HOLIDAY_ID = "593ba134249c7a2d4ed14c1a2d89d0a4"
MENU_ID = "021eed5e4226b4f4245debe9ccba0f1b"

APP_IDS = {
    "studio": STUDIO_ID,
    "watchlist": WATCHLIST_ID,
    "followups": FOLLOWUPS_ID,
    "stock": STOCK_ID,
    "shifts": SHIFTS_ID,
    "expenses": EXPENSES_ID,
    "holiday": HOLIDAY_ID,
    "menu": MENU_ID,
}

FEATURED_KEYS = ["studio", "watchlist", "stock", "shifts"]

PRESETS = [
    {"id": "ocean", "label": "Ocean", "color": "#2563eb"},
    {"id": "forest", "label": "Forest", "color": "#15803d"},
    {"id": "sunset", "label": "Sunset", "color": "#c2410c"},
    {"id": "plum", "label": "Plum", "color": "#7c3aed"},
    {"id": "graphite", "label": "Graphite", "color": "#334155"},
    {"id": "rose", "label": "Rose", "color": "#be185d"},
]

SUGGESTIONS = [
    {
        "id": "watchlist",
        "label": "A stock watchlist with price alerts",
        "prompt": "A stock watchlist with price alerts when something drops.",
    },
    {
        "id": "shifts",
        "label": "Staff shifts for my café",
        "prompt": "Staff shifts for my café, so the week is covered.",
    },
    {"id": "stock", "label": "Stock room counts", "prompt": "Stock room counts for the studio supplies."},
    {
        "id": "followups",
        "label": "Client follow-ups",
        "prompt": "Client follow-ups, the calls I still owe this week.",
    },
]

HOME_COPY = {
    "greeting": "Good afternoon, Lena",
    "headline": "What should we make today?",
    "prompt": "Invoices for my design studio. Send them, see who has paid, remind late clients by email.",
    "suggestionsLabel": "People are making:",
    "shelfTitle": "Your apps",
}

PROMPT_DRAFTS = [
    {"match": "invoice", "id": "studio"},
    {"match": "shift", "id": "shifts"},
    {"match": "café", "id": "shifts"},
    {"match": "cafe", "id": "shifts"},
]

SHELF_COPY = {
    "title": "My apps",
    "makeLabel": "Make an app",
    "filters": [
        {"id": "all", "label": "All"},
        {"id": "live", "label": "Live"},
        {"id": "building", "label": "Being made"},
    ],
    "empty": "Nothing on the shelf matches that.",
    "sharedTitle": "Shared with me",
    "sharedEmpty": "Nothing has been shared with you yet.",
}


def preset(preset_id: str) -> dict:
    found = next((item for item in PRESETS if item["id"] == preset_id), None)
    if found is None:
        raise KeyError(preset_id)
    return found


def live_path(app_id: str) -> str:
    return f"/{app_id}"


def _app(
    *,
    key: str,
    sort: int,
    slug: str,
    name: str,
    summary: str,
    status: str,
    status_label: str,
    labels: list,
    preset_id: str,
    icon: str,
    path: str,
    external: bool,
    shared_by: str | None = None,
    is_new: bool = False,
    badge: str | None = None,
    progress: int | None = None,
    workspace: dict | None = None,
) -> dict:
    look = preset(preset_id)
    document = {
        "_id": APP_IDS[key],
        "sort": sort,
        "slug": slug,
        "name": name,
        "summary": summary,
        "detail": summary,
        "status": status,
        "statusLabel": status_label,
        "labels": labels,
        "preset": preset_id,
        "color": look["color"],
        "icon": icon,
        "isNew": is_new,
        "badge": badge,
        "progress": progress,
        "path": path,
        "external": external,
        "sharedBy": shared_by,
        "workspace": workspace,
    }
    if not shared_by:
        document["draftKey"] = key
    return document


def _empty_panel(title: str, empty: str) -> dict:
    return {
        "title": title,
        "empty": empty,
        "stats": [],
        "columns": [],
        "rows": [],
        "chartTitle": "",
        "chartStart": "",
        "chartEnd": "",
        "bars": [],
    }


def studio_workspace() -> dict:
    color = preset("forest")["color"]
    return {
        "slug": "studio-invoices",
        "name": "Studio Invoices",
        "preset": "forest",
        "color": color,
        "icon": "lucideReceipt",
        "primaryAction": "New invoice",
        "secondaryAction": "Export",
        "madeWithLabel": "Made with baze · safety check",
        "madeWithPath": "/ready/studio",
        "sections": [
            {
                "id": "invoices",
                "label": "Invoices",
                "panel": {
                    "title": "Invoices",
                    "empty": None,
                    "stats": [
                        {"label": "Waiting to be paid", "value": "€8,240", "note": None},
                        {"label": "Paid in November", "value": "€14,900", "note": "+18% on October"},
                        {"label": "Late", "value": "2 clients", "note": None},
                        {"label": "Average time to pay", "value": "11 days", "note": None},
                    ],
                    "columns": ["No.", "Client", "Amount", "Status"],
                    "rows": [
                        {
                            "id": "0141",
                            "cells": ["#0141", "Nordlicht Café", "€2,400"],
                            "badge": None,
                            "action": "12 days late · Remind",
                        },
                        {
                            "id": "0140",
                            "cells": ["#0140", "Weber & Söhne", "€980"],
                            "badge": {"label": "5 days late", "tone": "warning"},
                            "action": None,
                        },
                        {
                            "id": "0139",
                            "cells": ["#0139", "Hofmann Architects", "€4,180"],
                            "badge": {"label": "Due in 6 days", "tone": "muted"},
                            "action": None,
                        },
                        {
                            "id": "0138",
                            "cells": ["#0138", "Saar Bikes", "€1,660"],
                            "badge": {"label": "Paid 2 Nov", "tone": "success"},
                            "action": None,
                        },
                        {
                            "id": "0137",
                            "cells": ["#0137", "Kaffeehaus Lindner", "€720"],
                            "badge": {"label": "Paid 30 Oct", "tone": "success"},
                            "action": None,
                        },
                    ],
                    "chartTitle": "Paid per week",
                    "chartStart": "7 weeks ago",
                    "chartEnd": "This week · €4,100",
                    "bars": [
                        {"height": 42, "current": False},
                        {"height": 55, "current": False},
                        {"height": 38, "current": False},
                        {"height": 64, "current": False},
                        {"height": 58, "current": False},
                        {"height": 76, "current": False},
                        {"height": 92, "current": True},
                    ],
                },
            },
            {
                "id": "clients",
                "label": "Clients",
                "panel": _empty_panel("Clients", "The people on your invoices show up here."),
            },
            {
                "id": "reminders",
                "label": "Reminders",
                "panel": _empty_panel("Reminders", "Late invoices get a reminder from your email."),
            },
            {
                "id": "settings",
                "label": "Settings",
                "panel": _empty_panel("Settings", "Reminders come from hello@lindner-studio.de."),
            },
        ],
    }


def catalog_apps() -> list[dict]:
    return [
        _app(
            key="studio",
            sort=0,
            slug="studio-invoices",
            name="Studio Invoices",
            summary="Send invoices and remind late clients.",
            status="live",
            status_label="Live",
            labels=[
                {"text": "New", "tone": "secondary"},
                {"text": "Take a look", "tone": "warning"},
                {"text": "Live", "tone": "success"},
            ],
            preset_id="forest",
            icon="lucideReceipt",
            path=live_path(STUDIO_ID),
            external=True,
            is_new=True,
            badge="New",
            workspace=studio_workspace(),
        ),
        _app(
            key="watchlist",
            sort=1,
            slug="stock-watchlist",
            name="Stock watchlist",
            summary="Price alerts when a stock drops.",
            status="live",
            status_label="Live",
            labels=[{"text": "Live", "tone": "success"}],
            preset_id="graphite",
            icon="lucideTrendingUp",
            path=live_path(WATCHLIST_ID),
            external=True,
        ),
        _app(
            key="followups",
            sort=2,
            slug="client-follow-ups",
            name="Client follow-ups",
            summary="The client calls you still need to make.",
            status="live",
            status_label="Live",
            labels=[{"text": "Live", "tone": "success"}],
            preset_id="ocean",
            icon="lucideUsers",
            path=live_path(FOLLOWUPS_ID),
            external=True,
        ),
        _app(
            key="stock",
            sort=3,
            slug="stock-room",
            name="Stock room",
            summary="Counts for the studio supplies.",
            status="attention",
            status_label="Take a look",
            labels=[{"text": "Take a look", "tone": "warning"}],
            preset_id="plum",
            icon="lucidePackage",
            path=live_path(STOCK_ID),
            external=True,
        ),
        _app(
            key="shifts",
            sort=4,
            slug="cafe-shifts",
            name="Café shifts",
            summary="Staff shifts so the café week is covered.",
            status="building",
            status_label="Being made",
            labels=[{"text": "Being made", "tone": "secondary"}],
            preset_id="sunset",
            icon="lucideCalendarDays",
            path="/building/shifts",
            external=False,
            progress=68,
        ),
        _app(
            key="expenses",
            sort=5,
            slug="team-expenses",
            name="Team expenses",
            summary="Log what the team spends.",
            status="paused",
            status_label="Paused",
            labels=[{"text": "Paused", "tone": "outline"}],
            preset_id="rose",
            icon="lucideWallet",
            path=live_path(EXPENSES_ID),
            external=True,
        ),
        _app(
            key="holiday",
            sort=6,
            slug="holiday-cover",
            name="Holiday cover",
            summary="Who covers the studio while people are away.",
            status="live",
            status_label="Live",
            labels=[{"text": "Live", "tone": "success"}],
            preset_id="ocean",
            icon="lucideCalendarDays",
            path=live_path(HOLIDAY_ID),
            external=True,
            shared_by="Nico Park",
        ),
        _app(
            key="menu",
            sort=7,
            slug="menu-board",
            name="Menu board",
            summary="The café menu, in one place.",
            status="live",
            status_label="Live",
            labels=[{"text": "Live", "tone": "success"}],
            preset_id="rose",
            icon="lucideUtensils",
            path=live_path(MENU_ID),
            external=True,
            shared_by="Jules Berg",
        ),
    ]


def _shots(items: list[tuple[str, str]], accent: str) -> list[dict]:
    return [{"id": shot_id, "name": name, "accent": accent} for shot_id, name in items]


def studio_draft() -> dict:
    look = preset("forest")
    return {
        "_id": "studio",
        "kicker": "Step 1 of 3 · Describe",
        "selectedPreset": "forest",
        "briefTitle": "What I’m making",
        "composerPlaceholder": "Tell me what to change…",
        "makeLabel": "Looks right, make it",
        "note": "You’ll see screenshots here while we shape it. Once it’s made, your app opens in its own browser tab.",
        "brief": [
            {"label": "Name", "value": "Studio Invoices", "swatch": None},
            {"label": "Its one job", "value": "Send invoices", "swatch": None},
            {"label": "Look", "value": look["label"], "swatch": look["color"]},
            {"label": "Views", "value": "Invoices, New invoice, Reminder email", "swatch": None},
            {"label": "Talks to", "value": "Your email only", "swatch": None},
        ],
        "messages": [
            {
                "id": "m1",
                "role": "you",
                "text": "Invoices for my design studio. Send them, see who has paid, and remind late clients by email.",
                "shots": [],
                "askPreset": False,
            },
            {
                "id": "m2",
                "role": "baze",
                "text": "Here’s a first look. Studio Invoices has one job, sending invoices, and three views:",
                "shots": _shots(
                    [("invoices", "Invoices"), ("new", "New invoice"), ("remind", "Reminder email")],
                    look["color"],
                ),
                "askPreset": True,
            },
            {
                "id": "m3",
                "role": "you",
                "text": "Reminders should come from hello@lindner-studio.de",
                "shots": [],
                "askPreset": False,
            },
        ],
        "build": {
            "kicker": "Step 2 of 3 · Making it",
            "title": "Studio Invoices is taking shape",
            "subtitle": "About a minute left. You can close this page, we’ll email you when it’s ready.",
            "steps": [
                {"id": "write", "label": "Writing it", "state": "done", "progress": 100},
                {"id": "try", "label": "Trying it safely", "state": "done", "progress": 100},
                {"id": "check", "label": "Checking it’s safe", "state": "active", "progress": 55},
                {"id": "ready", "label": "Ready for you", "state": "waiting", "progress": 0},
            ],
            "noticeTitle": "We stopped one thing",
            "noticeBody": (
                "Your app tried to send invoice details to an outside PDF service. We switched it to a "
                "built-in PDF maker, so your clients’ details stay with you. Nothing left the safe space."
            ),
            "waitingTitle": "While you wait",
            "waitingBody": (
                "We’re creating test invoices, marking them paid and sending practice reminders, all "
                "inside a sealed space that can only reach your email."
            ),
        },
        "ready": {
            "kicker": "Step 3 of 3 · Ready",
            "title": "Studio Invoices is ready",
            "address": "baze.app/studio-invoices · Forest look",
            "color": look["color"],
            "icon": "lucideReceipt",
            "facts": [
                {"label": "Its one job", "value": "Send invoices", "swatch": None},
                {"label": "Views", "value": "Invoices, New invoice, Reminder email", "swatch": None},
                {"label": "Look", "value": "Forest", "swatch": look["color"]},
                {"label": "Reminders come from", "value": "hello@lindner-studio.de", "swatch": None},
            ],
            "openLabel": "Open your app",
            "openPath": live_path(STUDIO_ID),
            "openHint": "It opens in its own browser tab with example clients, so you can try it. Baze stays here.",
            "safetyTitle": "Safety check",
            "checks": [
                {"id": "works", "tone": "pass", "text": "It works. We made, paid and reminded test invoices."},
                {"id": "email", "tone": "pass", "text": "It only talks to your email."},
                {"id": "place", "tone": "pass", "text": "Client details stay in Frankfurt, inside the EU."},
                {"id": "pdf", "tone": "changed", "text": "An outside PDF service was swapped for a built-in one."},
            ],
            "publishLabel": "Put it live",
            "shareLabel": "Share the safety check",
        },
    }


def shifts_draft() -> dict:
    look = preset("sunset")
    return {
        "_id": "shifts",
        "kicker": "Step 1 of 3 · Describe",
        "selectedPreset": "sunset",
        "briefTitle": "What I’m making",
        "composerPlaceholder": "Tell me what to change…",
        "makeLabel": "Looks right, make it",
        "note": "You’ll see screenshots here while we shape it. Once it’s made, your app opens in its own browser tab.",
        "brief": [
            {"label": "Name", "value": "Café shifts", "swatch": None},
            {"label": "Its one job", "value": "Cover the week", "swatch": None},
            {"label": "Look", "value": look["label"], "swatch": look["color"]},
            {"label": "Views", "value": "This week, Open shift", "swatch": None},
            {"label": "Talks to", "value": "Your email only", "swatch": None},
        ],
        "messages": [
            {
                "id": "s1",
                "role": "you",
                "text": "Staff shifts for my café, so the week is covered.",
                "shots": [],
                "askPreset": False,
            },
            {
                "id": "s2",
                "role": "baze",
                "text": "Café shifts has one job, covering the week. Two views so far:",
                "shots": _shots([("week", "This week"), ("open", "Open shift")], look["color"]),
                "askPreset": True,
            },
        ],
        "build": {
            "kicker": "Step 2 of 3 · Making it",
            "title": "Café shifts is taking shape",
            "subtitle": "About a minute left. You can close this page, we’ll email you when it’s ready.",
            "steps": [
                {"id": "write", "label": "Writing it", "state": "done", "progress": 100},
                {"id": "try", "label": "Trying it safely", "state": "done", "progress": 100},
                {"id": "check", "label": "Checking it’s safe", "state": "active", "progress": 55},
                {"id": "ready", "label": "Ready for you", "state": "waiting", "progress": 0},
            ],
            "noticeTitle": "We stopped one thing",
            "noticeBody": (
                "The rota tried to load names from an outside scheduling site. We kept the names you "
                "already typed, and nothing left the safe space."
            ),
            "waitingTitle": "While you wait",
            "waitingBody": "We’re filling a practice week and checking that every open shift has a person.",
        },
        "ready": {
            "kicker": "Step 3 of 3 · Ready",
            "title": "Café shifts is ready",
            "address": "baze.app/cafe-shifts · Sunset look",
            "color": look["color"],
            "icon": "lucideCalendarDays",
            "facts": [
                {"label": "Its one job", "value": "Cover the week", "swatch": None},
                {"label": "Views", "value": "This week, Open shift", "swatch": None},
                {"label": "Look", "value": look["label"], "swatch": look["color"]},
                {"label": "Talks to", "value": "Your email only", "swatch": None},
            ],
            "openLabel": "Open your app",
            "openPath": live_path(SHIFTS_ID),
            "openHint": "It opens in its own browser tab. Baze stays here.",
            "safetyTitle": "Safety check",
            "checks": [
                {"id": "works", "tone": "pass", "text": "It works. We filled a practice week."},
                {"id": "email", "tone": "pass", "text": "It only talks to your email."},
                {"id": "outside", "tone": "changed", "text": "An outside scheduling site was left unused."},
            ],
            "publishLabel": "Put it live",
            "shareLabel": "Share the safety check",
        },
    }


def catalog_drafts() -> list[dict]:
    return [studio_draft(), shifts_draft()]

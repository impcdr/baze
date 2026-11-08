"""Favicon for a hosted app. Same drawing as the Angular shelf tile."""

from __future__ import annotations

import re

# Lucide glyphs from the same set the shelf renders. Inner markup only.
_ICONS = {
    "lucideArrowRight": '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>',
    "lucideArrowUpRight": '<path d="M7 7h10v10"></path><path d="M7 17 17 7"></path>',
    "lucideCalendarDays": '<path d="M8 2v4"></path><path d="M16 2v4"></path><rect width="18" height="18" x="3" y="4" rx="2"></rect><path d="M3 10h18"></path><path d="M8 14h.01"></path><path d="M12 14h.01"></path><path d="M16 14h.01"></path><path d="M8 18h.01"></path><path d="M12 18h.01"></path><path d="M16 18h.01"></path>',
    "lucideCheck": '<path d="M20 6 9 17l-5-5"></path>',
    "lucideBike": '<circle cx="18.5" cy="17.5" r="3.5"></circle><circle cx="5.5" cy="17.5" r="3.5"></circle><circle cx="15" cy="5" r="1"></circle><path d="M12 17.5V14l-3-3 4-3 2 3h2"></path>',
    "lucideList": '<path d="M3 5h.01"></path><path d="M3 12h.01"></path><path d="M3 19h.01"></path><path d="M8 5h13"></path><path d="M8 12h13"></path><path d="M8 19h13"></path>',
    "lucideMail": '<path d="m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7"></path><rect x="2" y="4" width="20" height="16" rx="2"></rect>',
    "lucideMapPin": '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"></path><circle cx="12" cy="10" r="3"></circle>',
    "lucideShoppingCart": '<circle cx="8" cy="21" r="1"></circle><circle cx="19" cy="21" r="1"></circle><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"></path>',
    "lucidePackage": '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><polyline points="3.29 7 12 12 20.71 7"></polyline><path d="m7.5 4.27 9 5.15"></path>',
    "lucidePlus": '<path d="M5 12h14"></path><path d="M12 5v14"></path>',
    "lucideReceipt": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"></path><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"></path><path d="M12 17.5v-11"></path>',
    "lucideSettings": '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"></path><circle cx="12" cy="12" r="3"></circle>',
    "lucideTrendingUp": '<path d="M16 7h6v6"></path><path d="m22 7-8.5 8.5-5-5L2 17"></path>',
    "lucideUsers": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><path d="M16 3.128a4 4 0 0 1 0 7.744"></path><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><circle cx="9" cy="7" r="4"></circle>',
    "lucideUtensils": '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"></path><path d="M7 2v20"></path><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"></path>',
    "lucideWallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"></path><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"></path>',
}

_RADIUS = 36
_ICON = 46
_ORIGIN = (100 - _ICON) // 2
_FALLBACK_COLOR = "#15803d"
_FALLBACK_ICON = "lucidePackage"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_LINK = '<link rel="icon" href="favicon.svg" type="image/svg+xml">'


def render_app_favicon(color: str, icon: str) -> str:
    """Square of the app colour with the same white Lucide glyph the shelf tile uses."""
    fill = color if _HEX.match(color or "") else _FALLBACK_COLOR
    body = _ICONS.get(icon) or _ICONS[_FALLBACK_ICON]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f'<rect width="100" height="100" rx="{_RADIUS}" fill="{fill}"/>'
        f'<svg x="{_ORIGIN}" y="{_ORIGIN}" width="{_ICON}" height="{_ICON}" viewBox="0 0 24 24" '
        'fill="none" stroke="#ffffff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        f"{body}</svg></svg>"
    )


def ensure_favicon_link(html: str) -> str:
    """Point a hosted page at the favicon written beside it."""
    if "favicon.svg" in html:
        return html
    lowered = html.lower()
    head = lowered.find("</head>")
    if head != -1:
        return html[:head] + _LINK + html[head:]
    body = lowered.find("<body")
    if body != -1:
        return html[:body] + f"<head>{_LINK}</head>" + html[body:]
    return html

"""Shelf status, and the public path that serves each app's container."""

from __future__ import annotations

import html
import re
from http import HTTPStatus
from urllib import error, request

import falcon

from baze_api.app_favicon import render_app_favicon
from baze_api.identity import address_allows
from baze_api.catalog import STUDIO_ID
from baze_api.db import apps
from baze_api.http import now_ms
from baze_api.settings import Settings
from baze_api.supervisor import public_allowlist

_APP_PATH = re.compile(r"^/([0-9a-f]{32})(/.*)?$")
_FAVICON_PATH = re.compile(r"^/favicon\.(?:svg|ico)$")
_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
_PASS_HEADERS = ("Content-Type", "Location", "Cache-Control", "Content-Disposition")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = request.build_opener(_NoRedirect)


def clear_fake_live(settings: Settings) -> None:
    """Shelf apps are not Live unless a container is actually serving them."""
    for document in apps(settings).find({"kind": {"$ne": "runtime"}, "status": "live"}):
        labels = [label for label in document.get("labels") or [] if label.get("text") != "Live"]
        apps(settings).update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "status": "stopped",
                    "statusLabel": "",
                    "labels": labels,
                    "updatedAt": now_ms(),
                }
            },
        )


def mark_studio_live(settings: Settings) -> None:
    document = apps(settings).find_one({"_id": STUDIO_ID})
    if document is None:
        return
    labels = [label for label in document.get("labels") or [] if label.get("text") != "Live"]
    labels.append({"text": "Live", "tone": "success"})
    apps(settings).update_one(
        {"_id": STUDIO_ID},
        {"$set": {"status": "live", "statusLabel": "Live", "labels": labels, "updatedAt": now_ms()}},
    )


class AppProxy:
    """Serve /{app id} from that app's container. The shelf stays a navigator."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        match = _APP_PATH.match(req.path)
        if match is None:
            return
        document = apps(self.settings).find_one({"_id": match.group(1), "kind": {"$ne": "runtime"}})
        if document is None:
            return
        if not address_allows(document):
            _plain(resp, falcon.HTTP_403, "This app was made from another address.")
            return
        suffix = match.group(2) or "/"
        if req.method in ("GET", "HEAD") and _FAVICON_PATH.match(suffix):
            _favicon(resp, document)
            return
        runtime = document.get("runtime") or {}
        if runtime.get("profile") == "quarantine":
            _plain(resp, falcon.HTTP_200, "This is a check, not an app.")
            return
        origin = _page_origin(document)
        if origin is None:
            name = document.get("name") or "This app"
            if document.get("status") == "attention":
                _plain(resp, falcon.HTTP_503, f"{name} is not deployed yet.")
            elif document.get("status") == "building" and runtime.get("boxReady"):
                _plain(resp, falcon.HTTP_503, f"{name} is being made.")
            else:
                _plain(resp, falcon.HTTP_503, f"{name} is off.")
            return
        if req.method in ("GET", "HEAD") and not match.group(2):
            resp.status = falcon.HTTP_302
            resp.set_header("Location", f"/{match.group(1)}/")
            resp.complete = True
            return
        target = f"{origin}{suffix}"
        if req.query_string:
            target = f"{target}?{req.query_string}"
        headers = {
            key: value
            for key, value in req.headers.items()
            if key.lower() not in _HOP_HEADERS
        }
        headers["Host"] = origin.split("://", 1)[-1]
        body = req.bounded_stream.read() if req.content_length else None
        upstream = request.Request(target, data=body or None, headers=headers, method=req.method)
        viewer = _viewer(self.settings)
        try:
            with _OPENER.open(upstream, timeout=30) as result:
                _relay(resp, result.status, result.headers, result.read(), document, viewer)
        except error.HTTPError as exc:
            _relay(resp, exc.code, exc.headers, exc.read(), document, viewer)
        except (OSError, error.URLError):
            _plain(resp, falcon.HTTP_502, "The app is not answering.")


def _page_origin(document: dict) -> str | None:
    """Where the page is being served. A box that is still being made answers on its own address."""
    runtime = document.get("runtime") or {}
    port = runtime.get("hostPort")
    if document.get("status") == "live" and isinstance(port, int):
        return f"http://127.0.0.1:{port}"
    if document.get("status") == "building" and runtime.get("boxReady"):
        addresses = [ip for ip in (runtime.get("boxIps") or []) if isinstance(ip, str) and ip]
        if addresses:
            return f"http://{addresses[-1]}:8080"
    return None


def _favicon(resp: falcon.Response, document: dict) -> None:
    payload = render_app_favicon(document.get("color") or "", document.get("icon") or "").encode()
    resp.status = falcon.HTTP_200
    resp.content_type = "image/svg+xml"
    resp.data = payload
    resp.cache_control = ["no-cache"]
    resp.complete = True


def _plain(resp: falcon.Response, status: str, text: str) -> None:
    resp.status = status
    resp.content_type = "text/plain; charset=utf-8"
    resp.text = text
    resp.complete = True


def _viewer(settings: Settings) -> dict:
    """The account already chosen in Baze. A missing cookie is the default account."""
    from baze_api.catalog import ACCOUNT_EMAILS, ACCOUNTS, USER_EMAIL
    from baze_api.db import users
    from baze_api.identity import current_email

    email = current_email() or USER_EMAIL
    if email not in ACCOUNT_EMAILS:
        email = USER_EMAIL
    fallback = next(account for account in ACCOUNTS if account["email"] == email)
    person = users(settings).find_one({"email": email}) or {}
    return {
        "name": person.get("name") or fallback["name"],
        "initials": person.get("initials") or fallback["initials"],
        "color": person.get("color") or fallback["color"],
        "ink": person.get("ink") or fallback["ink"],
    }


def _relay(resp: falcon.Response, status: int, headers, payload: bytes, document: dict | None = None, viewer: dict | None = None) -> None:
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        phrase = "Unknown"
    resp.status = f"{status} {phrase}"
    content_type = headers.get("Content-Type") if headers is not None else ""
    html_page = document is not None and _html_utf8(content_type or "")
    if html_page:
        payload = inject_band(payload, document, viewer)
    resp.data = payload
    if headers is not None:
        for key in _PASS_HEADERS:
            value = headers.get(key)
            if value:
                resp.set_header(key, value)
    if html_page:
        policy = connect_policy(document)
        if policy:
            resp.set_header("Content-Security-Policy", policy)
    resp.complete = True


_CSP_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


def connect_policy(document: dict) -> str | None:
    """Browser calls from an isolated app may reach only the sites the person approved."""
    runtime = document.get("runtime") or {}
    if not runtime.get("isolated") or runtime.get("released"):
        return None
    if runtime.get("profile") == "web":
        return None
    sources = ["'self'"]
    for host in public_allowlist(document)[0]:
        name = host.lower().rstrip(".")
        if not _CSP_HOST.match(name):
            continue
        sources.append(f"https://{name}")
        sources.append(f"http://{name}")
    return "connect-src " + " ".join(sources)


def _html_utf8(content_type: str) -> bool:
    lowered = content_type.lower()
    if not lowered.startswith("text/html"):
        return False
    if "charset=" in lowered and "utf-8" not in lowered and "utf8" not in lowered:
        return False
    return True


_BAND_PX = 36
_BAND_FONT = "https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@800&display=swap"
_BAND_SAMPLE = (
    '<script id="baze-band-sample">'
    + r"""(function(){
function parse(color){var m=/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/.exec(color||'');
if(!m)return null;return [+m[1],+m[2],+m[3],m[4]===undefined?1:+m[4]];}
function over(front,back){var a=front[3]+back[3]*(1-front[3]);if(a<=0)return back;
function ch(i){return Math.round((front[i]*front[3]+back[i]*back[3]*(1-front[3]))/a);}
return [ch(0),ch(1),ch(2),a];}
function css(rgb){return 'rgb('+rgb[0]+','+rgb[1]+','+rgb[2]+')';}
function sample(x,y){var node=document.elementFromPoint(x,y),layers=[],seen=0;
while(node&&seen<16){seen++;
if(node.id!=='baze-band'){var bg=parse(getComputedStyle(node).backgroundColor);if(bg&&bg[3]>0.05)layers.push(bg);}
if(node===document.documentElement)break;node=node.parentElement;}
var acc=[255,255,255,1];for(var i=layers.length-1;i>=0;i--)acc=over(layers[i],acc);return acc;}
function ink(rgb){var y=(0.2126*rgb[0]+0.7152*rgb[1]+0.0722*rgb[2])/255;return y>0.62?'#0b1b3f':'#ffffff';}
function tone(el,y){var box=el.getBoundingClientRect(),xs=[box.left+6,(box.left+box.right)/2,Math.max(box.left+6,box.right-6)];
var acc=[0,0,0,0];xs.forEach(function(x){var rgb=sample(Math.min(Math.max(x,0),window.innerWidth-1),y);acc[0]+=rgb[0];acc[1]+=rgb[1];acc[2]+=rgb[2];});
var n=xs.length,rgb=[acc[0]/n,acc[1]/n,acc[2]/n,1],color=ink(rgb);
el.style.color=color;
el.style.textShadow=color==='#ffffff'?'0 0 2px rgba(0,0,0,.9),0 1px 1px rgba(0,0,0,.75)':'0 0 2px rgba(255,255,255,.95),0 1px 1px rgba(255,255,255,.8)';}
function paint(){var band=document.getElementById('baze-band');if(!band)return;
var y=band.offsetHeight+1,width=Math.max(window.innerWidth,1),count=12,colors=[];
for(var i=0;i<count;i++)colors.push(sample(Math.round((i+0.5)*width/count),y));
var same=colors.every(function(rgb){return css(rgb)===css(colors[0]);});
band.style.background=same?css(colors[0]):'linear-gradient(90deg,'+colors.map(function(rgb,i){
return css(rgb)+' '+((i/count)*100).toFixed(2)+'% '+(((i+1)/count)*100).toFixed(2)+'%';}).join(',')+')';
['baze-band-name','baze-band-user-name','baze-band-mark'].forEach(function(id){var el=document.getElementById(id);if(el)tone(el,y);});}
function schedule(){requestAnimationFrame(paint);}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule);else schedule();
window.addEventListener('load',schedule);window.addEventListener('resize',schedule);
[250,800,2000].forEach(function(ms){setTimeout(schedule,ms);});
})();"""
    + "</script>"
)


def inject_band(payload: bytes, document: dict, viewer: dict | None = None) -> bytes:
    """Pin a clear band to the top and keep the app's own content below it."""
    try:
        page = payload.decode("utf-8")
    except UnicodeError:
        return payload
    if 'id="baze-band"' in page:
        return payload
    match = re.search(r"<body\b[^>]*>", page, re.IGNORECASE)
    if match is None:
        return payload
    app_id = document.get("_id") or ""
    name = html.escape(str(document.get("name") or "App"))
    person = viewer or {}
    who = html.escape(str(person.get("name") or ""))
    initials = html.escape(str(person.get("initials") or ""))
    chip = html.escape(str(person.get("color") or "#334155"), quote=True)
    ink = html.escape(str(person.get("ink") or "#ffffff"), quote=True)
    logo = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="34" height="18" viewBox="4 42 94 50" '
        'aria-hidden="true" style="display:block;flex:none">'
        '<rect x="6" y="80" width="88" height="8" rx="4" fill="currentColor"></rect>'
        '<rect x="9" y="52" width="26" height="26" rx="7" fill="#1a5ce6"></rect>'
        '<rect x="38" y="52" width="26" height="26" rx="7" fill="#8db0ff"></rect>'
        '<rect x="70" y="52" width="26" height="26" rx="7" fill="#22c79b" transform="rotate(-12 70 78)"></rect>'
        "</svg>"
    )
    band = (
        f'<link rel="stylesheet" href="{_BAND_FONT}">'
        '<style id="baze-band-offset">'
        f"body{{padding-top:{_BAND_PX}px !important;box-sizing:border-box !important}}"
        "</style>"
        f'<div id="baze-band" style="position:fixed;top:0;left:0;right:0;height:{_BAND_PX}px;z-index:2147483646;'
        "display:flex;align-items:center;gap:10px;padding:0 14px;box-sizing:border-box;background:transparent;"
        "color:#0b1b3f;"
        "font:800 14px/1 'Red Hat Display',system-ui,sans-serif;letter-spacing:-0.03em;pointer-events:none\">"
        f'<img src="/{app_id}/favicon.svg" alt="" width="18" height="18" '
        'style="display:block;width:18px;height:18px;flex:none">'
        f'<span id="baze-band-name" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{name}</span>'
        f'<span id="baze-band-user" style="margin-left:auto;flex:none;display:inline-flex;align-items:center;gap:8px">'
        f'<span aria-hidden="true" style="width:22px;height:22px;border-radius:999px;display:grid;place-items:center;'
        f"background:{chip};color:{ink};font:800 10px/1 'Red Hat Display',system-ui,sans-serif;text-shadow:none\">{initials}</span>"
        f'<span id="baze-band-user-name" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{who}</span>'
        "</span>"
        '<span id="baze-band-mark" style="flex:none;display:inline-flex;align-items:center;gap:8px">'
        f"{logo}made with baze</span>"
        "</div>"
        f"{_BAND_SAMPLE}"
    )
    return (page[: match.end()] + band + page[match.end() :]).encode("utf-8")

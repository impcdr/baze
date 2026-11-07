from baze_api.app_favicon import ensure_favicon_link, render_app_favicon
from baze_api.studio_page import refresh_app_favicon


def test_favicon_uses_the_shelf_tile_geometry():
    svg = render_app_favicon("#15803d", "lucideReceipt")
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">')
    assert '<rect width="100" height="100" rx="36" fill="#15803d"/>' in svg
    assert '<svg x="27" y="27" width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="#ffffff"' in svg
    assert "M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2" in svg


def test_unknown_icon_and_colour_fall_back():
    svg = render_app_favicon("forest", "lucideMissing")
    assert 'fill="#15803d"' in svg
    assert "M11 21.73a2 2 0 0 0 2 0l7-4" in svg


def test_refresh_rewrites_an_existing_favicon_and_leaves_the_page(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    page = app / "index.html"
    page.write_text("<!doctype html><html><body><h1>Keep me</h1></body></html>")
    (app / "favicon.svg").write_text("<svg></svg>")
    refresh_app_favicon(str(tmp_path), "#334155", "lucideTrendingUp")
    written = (app / "favicon.svg").read_text()
    assert 'fill="#334155"' in written
    assert "M16 7h6v6" in written
    text = page.read_text()
    assert "Keep me" in text
    assert 'href="favicon.svg"' in text


def test_a_written_page_keeps_the_favicon_link():
    linked = ensure_favicon_link("<!doctype html><html><body><h1>Pulse</h1></body></html>")
    assert '<link rel="icon" href="favicon.svg" type="image/svg+xml">' in linked
    assert linked.index("<head>") < linked.index("<body")
    already = ensure_favicon_link('<html><head><link rel="icon" href="favicon.svg"></head><body></body></html>')
    assert already.count("favicon.svg") == 1

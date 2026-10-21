import json
import re

from amagi_vaultgraph.graph import build_graph
from amagi_vaultgraph.render import CDN_URL, _sri, graph_data, render_html, safe_json, vendored_js
from amagi_vaultgraph.vault import scan_vault

SECRET = "ACCOUNT NUMBER 991-22-7731"
EVIL = "evil</script><img src=x onerror=alert(1)>"


def demo_graph(make_vault):
    return build_graph(scan_vault(make_vault({
        "a.md": f"---\ntype: concept\n---\n{SECRET}\n[[b]]",
        "b.md": "---\ntype: person\n---\nshort body",
        "evil.md": "---\ntitle: " + EVIL + "\n---\n[[a]]",
    })))


def page_data(page):
    m = re.search(r"const DATA=(\{.*?\});\n", page)
    assert m, "DATA block not found"
    return json.loads(m.group(1))


def test_vendored_library_is_present():
    js = vendored_js()
    assert len(js) > 1_000_000 and "ForceGraph3D" in js


def test_default_page_has_names_but_no_note_text(make_vault):
    page = render_html(demo_graph(make_vault), title="t", version="0")
    assert SECRET not in page and "short body" not in page
    data = page_data(page)
    assert sorted(n["path"] for n in data["nodes"]) == ["a", "b", "evil"]
    assert all("excerpt" not in n for n in data["nodes"])


def test_excerpts_only_when_asked(make_vault):
    page = render_html(demo_graph(make_vault), title="t", version="0", with_excerpts=True)
    assert SECRET in page
    assert {n["path"]: n.get("excerpt") for n in page_data(page)["nodes"]}["b"] == "short body"


def test_hostile_note_name_cannot_close_the_script_tag(make_vault):
    page = render_html(demo_graph(make_vault), title="</title><script>x</script>", version="0")
    assert "<img src=x" not in page
    assert "<title>&lt;/title&gt;&lt;script&gt;x&lt;/script&gt;</title>" in page
    assert "evil\\u003c/script\\u003e" in page
    assert EVIL in [n["name"] for n in page_data(page)["nodes"]]


def test_safe_json_escapes_line_separators():
    out = safe_json({"k": "a\u2028b<&>"})
    assert "\u2028" not in out and json.loads(out) == {"k": "a\u2028b<&>"}


def test_offline_inlines_library_and_cdn_uses_sri(make_vault):
    g = demo_graph(make_vault)
    offline = render_html(g, title="t", version="0")
    assert "ForceGraph3D" in offline and "cdn.jsdelivr" not in offline
    assert not re.search(r"<script[^>]+src=", offline)
    cdn = render_html(g, title="t", version="0", offline=False)
    assert len(cdn) < 100_000
    assert f'src="{CDN_URL}" integrity="{_sri(vendored_js())}"' in cdn
    assert _sri(vendored_js()).startswith("sha384-")


def test_layered_data_pins_every_node_and_labels_columns(make_vault):
    g = demo_graph(make_vault)
    data = graph_data(g, layered=True)
    assert all({"fx", "fy", "fz"} <= set(n) for n in data["nodes"])
    assert [c["group"] for c in data["columns"]] == g.group_order
    assert all("fx" not in n for n in graph_data(g)["nodes"])
    assert '"layered":true' in render_html(g, title="t", version="0", layered=True)


def test_node_size_tracks_degree_and_legend_counts(make_vault):
    g = demo_graph(make_vault)
    data = graph_data(g)
    by_path = {n["path"]: n for n in data["nodes"]}
    assert by_path["a"]["deg"] == 2 and by_path["a"]["val"] == 3
    assert sum(item["count"] for item in data["legend"]) == 3
    assert len(data["links"]) == 2

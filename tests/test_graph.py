from pathlib import Path

import pytest

from amagi_vaultgraph.graph import NO_GROUP, PALETTE, build_graph, layered_positions, pick_color_mode
from amagi_vaultgraph.vault import Note, scan_vault


def graph_for(make_vault, files, color_by="auto"):
    return build_graph(scan_vault(make_vault(files)), color_by)


def bare(stem, folder=""):
    return Note(id=(folder + "/" if folder else "") + stem, path=Path(stem), stem=stem, folder=folder, name=stem)


def test_resolves_by_stem_title_alias_and_path(make_vault):
    g = graph_for(make_vault, {
        "a.md": "[[B]] [[Gamma Title]] [[the d]] [[sub/e]]",
        "b.md": "",
        "c.md": "---\ntitle: Gamma Title\n---\n",
        "d.md": "---\naliases: [The D]\n---\n",
        "sub/e.md": "",
    })
    assert g.edges == {("a", "b"), ("a", "c"), ("a", "d"), ("a", "sub/e")}
    assert g.dangling == []


def test_spaces_underscores_and_hyphens_match(make_vault):
    g = graph_for(make_vault, {"a.md": "[[project alpha thing]] [[Other-Note]]",
                               "project_alpha_thing.md": "", "other_note.md": ""})
    assert g.edges == {("a", "project_alpha_thing"), ("a", "other_note")}


def test_relative_markdown_links(make_vault):
    g = graph_for(make_vault, {"x/a.md": "[up](../b.md) [same](c.md)", "b.md": "", "x/c.md": ""})
    assert g.edges == {("x/a", "b"), ("x/a", "x/c")}


def test_ambiguous_name_goes_to_the_same_folder(make_vault):
    g = graph_for(make_vault, {"p/a.md": "[[index]]", "p/index.md": "", "q/index.md": "", "q/b.md": "[[index]]"})
    assert g.edges == {("p/a", "p/index"), ("q/b", "q/index")}


def test_self_links_dropped_and_dangling_recorded_once(make_vault):
    g = graph_for(make_vault, {"a.md": "[[a]] [[missing]] [[missing]] [[b]]", "b.md": "[[a]]"})
    assert g.edges == {("a", "b"), ("b", "a")}
    assert g.dangling == [("a", "missing")]
    assert g.undirected_edges == [("a", "b")]
    assert g.degree("a") == 1 and g.degree("b") == 1


def test_orphan_has_no_links_in_or_out(make_vault):
    g = graph_for(make_vault, {"a.md": "[[b]]", "b.md": "", "lonely.md": "[[nowhere]]"})
    assert [n.id for n in g.orphans()] == ["lonely"]


def test_auto_colour_prefers_type_when_most_notes_have_one(make_vault):
    notes = scan_vault(make_vault({"a.md": "---\ntype: x\n---\n", "b.md": "---\ntype: y\n---\n", "c.md": ""}))
    assert pick_color_mode(notes) == "type"


def test_auto_colour_falls_back_to_folder_then_prefix():
    assert pick_color_mode([bare("a", "x"), bare("b", "y")]) == "folder"
    assert pick_color_mode([bare("project_a"), bare("project_b"), bare("feedback_c")]) == "prefix"
    assert pick_color_mode([bare("alpha"), bare("beta")]) == "folder"


def test_explicit_colour_modes(make_vault):
    files = {"p/project_a.md": "---\ntype: t1\ntags: [red, blue]\n---\n", "q/feedback_b.md": ""}
    groups = {m: build_graph(scan_vault(make_vault(files)), m).groups for m in ("type", "folder", "prefix", "tag")}
    assert groups["type"] == {"p/project_a": "t1", "q/feedback_b": NO_GROUP}
    assert groups["folder"] == {"p/project_a": "p", "q/feedback_b": "q"}
    assert groups["prefix"] == {"p/project_a": "project", "q/feedback_b": "feedback"}
    assert groups["tag"] == {"p/project_a": "red", "q/feedback_b": NO_GROUP}


def test_unknown_colour_mode_rejected():
    with pytest.raises(ValueError):
        build_graph([bare("a")], "colour")


def test_group_order_and_palette(make_vault):
    g = graph_for(make_vault, {
        "a.md": "---\ntype: concept\n---\n", "b.md": "---\ntype: concept\n---\n",
        "c.md": "---\ntype: person\n---\n", "d.md": "",
    }, "type")
    assert g.group_order == ["concept", "person", NO_GROUP]
    assert g.colors["concept"] == PALETTE[0] and g.colors["person"] == PALETTE[1]
    assert g.groups["d"] == NO_GROUP


def test_groups_past_the_palette_get_stable_hex_colours(make_vault):
    files = {f"f{i:02}/n.md": "" for i in range(len(PALETTE) + 3)}
    g1 = graph_for(make_vault, files, "folder")
    g2 = build_graph(scan_vault(make_vault(files)), "folder")
    assert len(g1.colors) == len(files)
    assert all(c.startswith("#") and len(c) == 7 for c in g1.colors.values())
    assert g1.colors == g2.colors


def test_layered_one_column_per_group(make_vault):
    g = graph_for(make_vault, {
        "a/1.md": "[[2]] [[3]]", "a/2.md": "", "a/3.md": "", "b/4.md": "[[1]]", "c/5.md": "",
    }, "folder")
    pos = layered_positions(g)
    xs = {grp: {pos[nid][0] for nid, gg in g.groups.items() if gg == grp} for grp in g.group_order}
    assert all(len(v) == 1 for v in xs.values())  # each group shares one x
    col_x = [next(iter(xs[grp])) for grp in g.group_order]
    assert col_x == sorted(col_x) and len(set(col_x)) == 3  # biggest group on the left
    assert pos["a/1"][1] > pos["a/2"][1]  # best-connected note on top
    assert layered_positions(g) == pos  # deterministic


def test_layered_tall_column_wraps_into_depth(make_vault):
    g = graph_for(make_vault, {f"n{i:02}.md": "" for i in range(40)}, "folder")
    assert len({p[2] for p in layered_positions(g).values()}) > 1

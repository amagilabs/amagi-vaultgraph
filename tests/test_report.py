from amagi_vaultgraph.graph import build_graph
from amagi_vaultgraph.report import (build_report, dangling_links, render_markdown, render_text,
                                     similar_names, unlinked_mentions)
from amagi_vaultgraph.vault import scan_vault


def graph_for(make_vault, files):
    return build_graph(scan_vault(make_vault(files)), "folder")


def pairs(suggestions):
    return {(s.source, s.target, s.reason) for s in suggestions}


def test_unlinked_mention_by_title_and_alias(make_vault):
    g = graph_for(make_vault, {
        "a.md": "We should use Event Sourcing here, and ask about the api gateway.",
        "event-sourcing.md": "---\ntitle: Event Sourcing\n---\n",
        "gw.md": "---\ntitle: Gateway Notes\naliases: [API Gateway]\n---\n",
    })
    assert pairs(unlinked_mentions(g)) == {("a", "event-sourcing", "mention"), ("a", "gw", "mention")}


def test_already_linked_notes_are_not_suggested(make_vault):
    g = graph_for(make_vault, {
        "a.md": "Event Sourcing again.",
        "b.md": "See [[a]]. Event Sourcing.",
        "event-sourcing.md": "Back to [[a]].",
    })
    assert ("a", "event-sourcing", "mention") not in pairs(unlinked_mentions(g))
    assert ("b", "event-sourcing", "mention") in pairs(unlinked_mentions(g))


def test_text_inside_a_link_is_not_an_unlinked_mention(make_vault):
    g = graph_for(make_vault, {"a.md": "[[other|Event Sourcing]]", "other.md": "", "event-sourcing.md": ""})
    assert unlinked_mentions(g) == []


def test_short_and_numeric_names_are_not_matched(make_vault):
    g = graph_for(make_vault, {
        "a.md": "home todo 2026-09-01 notes",
        "home.md": "", "todo.md": "", "2026-09-01.md": "",
    })
    assert unlinked_mentions(g) == []


def test_name_found_in_many_notes_is_treated_as_a_common_word(make_vault):
    files = {f"n{i:02}.md": "talked to the client today" for i in range(20)}
    files["client.md"] = ""
    files["x.md"] = "budget review"
    files["budget.md"] = ""
    found = pairs(unlinked_mentions(graph_for(make_vault, files)))
    assert not any(t == "client" for _s, t, _r in found)  # in 20 of 22 notes
    assert ("x", "budget", "mention") in found


def test_similar_names_for_orphans_use_rare_words(make_vault):
    g = graph_for(make_vault, {
        "project_invoice_export.md": "[[project_alpha]]",
        "project_alpha.md": "",
        "project_beta.md": "[[project_alpha]]",
        "invoice-export.md": "",
        "project_gamma.md": "",
    })
    found = similar_names(g)
    # sharing "invoice export" is a strong hint; sharing only "project" is not
    assert [(s.source, s.target) for s in found] == [("invoice-export", "project_invoice_export")]
    assert float(found[0].detail) >= 0.25


def test_plural_is_close_enough(make_vault):
    g = graph_for(make_vault, {"webhooks.md": "[[x]]", "x.md": "", "webhook-signing.md": ""})
    assert ("webhook-signing", "webhooks") in {(s.source, s.target) for s in similar_names(g)}


def test_dangling_did_you_mean(make_vault):
    g = graph_for(make_vault, {"a.md": "[[rate-limitting]] [[zzz qqq]]", "rate-limiting.md": ""})
    d = {x.target: x.did_you_mean for x in dangling_links(g)}
    assert d == {"rate-limitting": "rate-limiting", "zzz qqq": None}


def test_report_orders_orphan_rescues_first_and_renders(make_vault):
    g = graph_for(make_vault, {
        "a.md": "Mentions Budget Planning and [[b]].", "b.md": "Budget Planning", "budget-planning.md": "[[c]]",
        "c.md": "", "budget-planning-old.md": "",
    })
    rep = build_report(g)
    assert [n.id for n in rep.orphans] == ["budget-planning-old"]
    assert rep.suggestions[0].source == "budget-planning-old"
    assert rep.stats["notes"] == 5 and rep.stats["orphans"] == 1
    text = render_text(rep, limit=1)
    assert "ORPHANS (1)" in text and "budget-planning-old" in text and "more (full list: --report FILE)" in text
    md = render_markdown(rep, "demo")
    assert md.startswith("# Vault report: demo") and "`budget-planning-old`" in md


def test_report_never_quotes_note_text(make_vault):
    secret = "the dock gate code is 4417-B"
    g = graph_for(make_vault, {"a.md": secret + " [[b]]", "b.md": "", "c.md": ""})
    rep = build_report(g)
    blob = render_text(rep, 100) + render_markdown(rep, "v") + repr(rep.as_dict())
    assert "4417-B" not in blob

from amagi_vaultgraph.vault import extract_links, parse_frontmatter, scan_vault, without_links

BOM = chr(0xFEFF)


def targets(text):
    return [(link.target, link.kind) for link in extract_links(text)]


def test_frontmatter_scalars_and_lists():
    fm, body = parse_frontmatter(
        "---\ntitle: \"My Note\"\ntype: concept\ntags: [a, 'b']\naliases:\n  - One\n  - Two\n---\nBody here\n"
    )
    assert fm["title"] == "My Note"
    assert fm["type"] == "concept"
    assert fm["tags"] == ["a", "b"]
    assert fm["aliases"] == ["One", "Two"]
    assert body == "Body here\n"


def test_frontmatter_nested_metadata_type_like_claude_memory():
    text = "---\nname: feedback-style\ndescription: how to work\nmetadata:\n  type: feedback\n  tags:\n    - x\n---\n\nRule.\n"
    fm, body = parse_frontmatter(text)
    assert fm["name"] == "feedback-style"
    assert fm["metadata"] == {"type": "feedback", "tags": ""}
    assert body.strip() == "Rule."


def test_frontmatter_crlf_and_bom():
    fm, body = parse_frontmatter(BOM + "---\r\ntype: daily\r\n---\r\nhello\r\n")
    assert fm == {"type": "daily"}
    assert body == "hello\r\n"


def test_frontmatter_block_scalar_does_not_leak_keys():
    fm, _ = parse_frontmatter("---\ndescription: >\n  type: not-a-type\n  more text\ntitle: Real\n---\n")
    assert "type" not in fm
    assert fm["title"] == "Real"


def test_no_frontmatter_returns_text_unchanged():
    text = "# Heading\n---\nnot frontmatter\n"
    assert parse_frontmatter(text) == ({}, text)


def test_wikilink_variants():
    text = "[[Plain]] [[Target|shown text]] [[Note#Heading]] [[Note2^block]] [[folder/Deep Note]] [[x.md]]"
    assert targets(text) == [
        ("Plain", "wiki"), ("Target", "wiki"), ("Note", "wiki"), ("Note2", "wiki"),
        ("folder/Deep Note", "wiki"), ("x", "wiki"),
    ]


def test_note_embeds_count_but_image_and_pdf_embeds_do_not():
    assert targets("![[diagram.png]] ![[photo.JPG|200]] ![[Some Note]] ![[file.pdf]]") == [("Some Note", "wiki")]


def test_same_note_heading_link_is_not_a_link():
    assert targets("see [[#Section]]") == []


def test_links_inside_code_are_ignored():
    text = "real [[A]]\n```\n[[B]] in a fence\n```\n`[[C]]` inline\n~~~md\n[[D]]\n~~~\n"
    assert targets(text) == [("A", "wiki")]


def test_markdown_links_to_notes_only():
    text = "[a](other.md) [b](../up/Note%20Two.md#part) [c](https://example.com/x.md) [d](image.png) ![e](pic.md)"
    assert targets(text) == [("other.md", "md"), ("../up/Note Two.md", "md")]


def test_without_links_removes_link_text():
    assert without_links("see [[Foo Bar]] and [label](x.md) ok").split() == ["see", "and", "ok"]


def test_scan_reads_names_types_and_skips_hidden_folders(make_vault):
    vault = make_vault({
        "a.md": "---\ntitle: Alpha\ntype: concept\naliases: [First]\n---\n[[b]]",
        "sub/b.markdown": "plain",
        ".obsidian/workspace.md": "[[a]]",
        "node_modules/pkg/readme.md": "x",
        "notes.txt": "[[a]]",
    })
    notes = scan_vault(vault)
    assert [n.id for n in notes] == ["a", "sub/b"]
    a, b = notes
    assert (a.name, a.type, a.aliases, a.folder) == ("Alpha", "concept", ["First"], "")
    assert [link.target for link in a.links] == ["b"]
    assert (b.name, b.type, b.folder, b.top_folder) == ("b", None, "sub", "sub")


def test_scan_reads_claude_memory_style_type(make_vault):
    vault = make_vault({"feedback_x.md": "---\nname: x rule\nmetadata:\n  type: feedback\n---\nbody"})
    note = scan_vault(vault)[0]
    assert (note.name, note.type) == ("x rule", "feedback")


def test_scan_exclude_globs(make_vault):
    vault = make_vault({"keep.md": "", "templates/t.md": "", "drafts/x.excalidraw.md": "", "drafts/y.md": ""})
    assert [n.id for n in scan_vault(vault, ["templates", "*.excalidraw.md"])] == ["drafts/y", "keep"]


def test_title_given_as_wikilink_property(make_vault):
    vault = make_vault({"n.md": "---\ntitle: \"[[Real Title]]\"\n---\n"})
    assert scan_vault(vault)[0].name == "Real Title"

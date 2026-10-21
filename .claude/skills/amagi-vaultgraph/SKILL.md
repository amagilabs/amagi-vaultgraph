---
name: amagi-vaultgraph
description: Map a folder of markdown notes (Obsidian vault, Claude Code memory folder, Foam or Logseq export) as a 3D link graph in one offline HTML file, and report orphan notes, dangling [[wikilinks]] and suggested links by name matching. Use when asked to visualise a vault or memory folder, find notes nothing links to, fix broken wikilinks, tidy a Claude Code memory index, or add a "no orphans / no broken links" check to CI.
---

# amagi-vaultgraph

A CLI that reads a folder of `.md` notes, treats each note as a node and each `[[wikilink]]` or
relative `.md` link as an edge, and writes one self-contained HTML file with a 3D graph. It also
prints a report: the most-linked notes, orphans, dangling links (with a "did you mean"), and
suggested links. Suggestions come from name matching only. No LLM, no network.

## When to use this skill

- The user wants to see how their notes or Claude Code memory files connect.
- The user asks which notes are orphaned, or which `[[links]]` point at nothing.
- The user wants link suggestions to clean up a vault or a `MEMORY.md` index.
- The user wants a CI or pre-commit check that fails on orphans or broken links.

## How to use it

Install once: `pipx install amagi-vaultgraph` (or `pip install -e .` from this repo in development).

```bash
vaultgraph path/to/vault                     # writes vaultgraph.html and prints the report
vaultgraph path/to/vault -o graph.html --layered   # one column per colour group
vaultgraph path/to/vault --no-html --report report.md --json graph.json
vaultgraph path/to/vault --check --no-html -q      # exit 1 on orphans or dangling links
vaultgraph path/to/vault --color-by folder --exclude templates --exclude "*.excalidraw.md"
```

`--color-by` takes `auto` (default), `type` (frontmatter `type`, or `metadata: type` as in Claude
Code memory files), `folder` (top folder), `prefix` (file-name prefix such as `project_` or
`feedback_`) or `tag` (first frontmatter tag). Exit codes: 0 ok, 1 `--check` found problems,
2 usage error (not a folder, no notes, bad option).

## Privacy rules

- By default the HTML holds note names, vault-relative paths and group names. It never holds note
  text. `--with-excerpts` adds the first ~280 characters of each note to the tooltips and prints a
  warning; only use it when the user asks and the file will not be shared.
- The library is inlined by default, so the page makes no network request. `--cdn` loads it from
  jsDelivr with a pinned SRI hash instead.
- When you share results with the user, quote note names and counts, not note contents.

## Working with the results

1. Run with `--no-html --json graph.json` and read `report.orphans`, `report.dangling`
   (`source`, `target`, `did_you_mean`) and `report.suggestions` (`source`, `target`, `reason`,
   `detail`).
2. For a dangling link with a `did_you_mean`, fix the typo in the source note. Without one, either
   create the missing note or remove the link. Ask before creating notes.
3. Treat suggestions as leads, not edits. A `mention` means the source note's text contains the
   target's name but the notes are not linked. A `similar-name` means an orphan shares rare words
   with the target's name. Open both notes and confirm before adding a link.
4. Re-run until the counts look right, or until `--check` exits 0.

## Limits

- Only `.md` and `.markdown` files. Dot-folders (`.obsidian`, `.git`, `.trash`) and dependency
  folders are skipped.
- The frontmatter reader handles the YAML subset notes use (scalars, lists, one nested level). It
  is not a full YAML parser.
- Logseq block references `((uuid))`, tags as links, and Dataview queries are not edges.
- Suggestions match names, not meaning. A note about "billing" will not be matched to "invoices".

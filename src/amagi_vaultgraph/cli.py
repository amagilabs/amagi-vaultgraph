"""Command line entry point: `vaultgraph VAULT [-o graph.html] [--layered] ...`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .graph import COLOR_MODES, build_graph
from .render import graph_data, render_html
from .report import build_report, render_markdown, render_text
from .vault import scan_vault


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vaultgraph",
        description="Turn a folder of markdown notes (Obsidian vault, Claude Code memory folder, "
                    "Foam or Logseq export) into one shareable 3D graph HTML file, plus an orphan "
                    "report and link suggestions. Embeds note names only, never note text.",
    )
    p.add_argument("vault", help="folder of .md notes")
    p.add_argument("-o", "--out", default="vaultgraph.html", help="HTML file to write (default: vaultgraph.html)")
    p.add_argument("--layered", action="store_true", help="arrange notes in columns, one per colour group")
    p.add_argument("--color-by", choices=COLOR_MODES, default="auto",
                   help="colour nodes by frontmatter type, top folder, file-name prefix or first tag "
                        "(default: auto)")
    net = p.add_mutually_exclusive_group()
    net.add_argument("--offline", dest="offline", action="store_true", default=True,
                     help="inline the graph library so the file works with no network (default)")
    net.add_argument("--cdn", dest="offline", action="store_false",
                     help="load the graph library from jsDelivr instead (smaller file, needs internet)")
    p.add_argument("--title", help="page title (default: the vault folder name)")
    p.add_argument("--spin", action="store_true", help="slowly orbit the camera after load (good for screen recordings)")
    p.add_argument("--with-excerpts", action="store_true",
                   help="ALSO embed the first ~280 characters of each note in hover tooltips. "
                        "Off by default: the file then contains note text.")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="skip files or folders matching GLOB (repeatable), e.g. --exclude 'templates' --exclude '*.excalidraw.md'")
    p.add_argument("--report", metavar="FILE", help="write the full orphan/dangling/suggestion report as markdown")
    p.add_argument("--json", metavar="FILE", help="write graph data and report as JSON (names only)")
    p.add_argument("--no-html", action="store_true", help="skip the HTML file; just report")
    p.add_argument("--check", action="store_true", help="exit 1 if there are orphans or dangling links (for CI or hooks)")
    p.add_argument("--limit", type=int, default=10, metavar="N", help="rows per section in the terminal summary (default: 10)")
    p.add_argument("-q", "--quiet", action="store_true", help="print only the one-line summary")
    p.add_argument("--version", action="version", version=f"amagi-vaultgraph {__version__}")
    return p


def _size(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 1_000_000 else f"{max(1, round(n / 1000))} KB"


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    args = _parser().parse_args(argv)
    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"vaultgraph: not a folder: {vault}", file=sys.stderr)
        return 2
    if args.limit < 0:
        print("vaultgraph: --limit must be 0 or more", file=sys.stderr)
        return 2

    notes = scan_vault(vault, args.exclude)
    if not notes:
        print(f"vaultgraph: no .md notes found under {vault}", file=sys.stderr)
        return 2
    graph = build_graph(notes, args.color_by)
    report = build_report(graph)
    st = report.stats
    label = vault.resolve().name or str(vault)

    print(f"{st['notes']} notes, {st['links']} links, {st['orphans']} orphans, "
          f"{st['dangling']} dangling links, {st['suggestions']} suggested links "
          f"(coloured by {st['color_by']}, {len(graph.group_order)} groups)")

    if not args.no_html:
        if args.with_excerpts:
            print("vaultgraph: --with-excerpts: the HTML file contains note text; check it before sharing",
                  file=sys.stderr)
        page = render_html(graph, title=args.title or label, version=__version__, layered=args.layered,
                           offline=args.offline, spin=args.spin, with_excerpts=args.with_excerpts)
        out = Path(args.out)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True)
        out.write_text(page, encoding="utf-8")
        mode = ("layered" if args.layered else "3d force") + (", offline" if args.offline else ", cdn")
        content = "names + excerpts" if args.with_excerpts else "names only"
        print(f"wrote {out} ({_size(len(page.encode('utf-8')))}, {mode}, {content})")

    if args.report:
        Path(args.report).write_text(render_markdown(report, label), encoding="utf-8")
        print(f"wrote {args.report}")
    if args.json:
        payload = {"graph": graph_data(graph, layered=args.layered), "report": report.as_dict()}
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.json}")

    if not args.quiet:
        print(render_text(report, args.limit))

    if args.check and (report.orphans or report.dangling):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

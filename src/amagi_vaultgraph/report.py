"""Orphan report and link suggestions. Name matching only: no embeddings,
no LLM, nothing leaves the machine. Output names notes, never quotes them."""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .graph import Graph, norm_key
from .vault import Note, without_links

_TOKEN_RE = re.compile(r"[^\W_]+", re.U)
MIN_SINGLE_WORD = 5  # one-word names shorter than this ("home", "todo") are too noisy to match in text
MAX_KEY_WORDS = 6


def tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Suggestion:
    source: str  # note id that should get the link
    target: str  # note id to link to
    reason: str  # "mention" or "similar-name"
    detail: str  # the name that matched, or the similarity score

    def as_dict(self) -> Dict[str, str]:
        return {"source": self.source, "target": self.target, "reason": self.reason, "detail": self.detail}


@dataclass
class Dangling:
    source: str
    target: str  # raw link text as written
    did_you_mean: Optional[str]  # note id

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {"source": self.source, "target": self.target, "did_you_mean": self.did_you_mean}


def _name_keys(note: Note) -> Set[Tuple[str, ...]]:
    keys = set()
    for k in {note.name, note.stem, *note.aliases}:
        t = tuple(tokens(k))
        if not t or len(t) > MAX_KEY_WORDS:
            continue
        if len(t) == 1 and len(t[0]) < MIN_SINGLE_WORD:
            continue
        if all(tok.isdigit() for tok in t):
            continue  # daily notes named 2026-03-04 match every date in the text
        keys.add(t)
    return keys


def unlinked_mentions(graph: Graph, max_share: float = 0.15) -> List[Suggestion]:
    """Note A's text names note B (by title, file name or alias) but A and B
    are not linked in either direction. Same idea as Obsidian's
    'unlinked mentions', run over the whole vault at once. A name that shows
    up in more than `max_share` of all notes is an everyday word in this vault
    ("claude", "accounts"), not a pointer, and is ignored."""
    index: Dict[Tuple[str, ...], Set[str]] = defaultdict(set)
    for n in graph.notes:
        for key in _name_keys(n):
            index[key].add(n.id)
    # a phrase that names many notes is not a reliable pointer to any of them
    index = {k: v for k, v in index.items() if len(v) <= 2}
    if not index:
        return []
    longest = max(len(k) for k in index)
    hits: Dict[str, Dict[str, Tuple[str, ...]]] = {}
    key_df: Counter = Counter()
    for a in graph.notes:
        words = tokens(without_links(a.body))  # linked mentions are not "unlinked mentions"
        found: Dict[str, Tuple[str, ...]] = {}
        for i in range(len(words)):
            for size in range(min(longest, len(words) - i), 0, -1):
                key = tuple(words[i:i + size])
                hit = index.get(key)
                if not hit:
                    continue
                for b in hit:
                    if b != a.id and b not in found:
                        found[b] = key
                break
        hits[a.id] = found
        key_df.update(set(found.values()))
    limit = max(3, int(max_share * len(graph.notes)))
    out: List[Suggestion] = []
    for a in graph.notes:
        for b, key in sorted(hits[a.id].items()):
            if key_df[key] > limit or b in graph.neighbors.get(a.id, ()):
                continue
            out.append(Suggestion(a.id, b, "mention", graph.by_id[b].name))
    return out


def _stem(tok: str) -> str:
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok


def similar_names(graph: Graph, only: Optional[List[Note]] = None, top: int = 3,
                  threshold: float = 0.25) -> List[Suggestion]:
    """For each note in `only` (default: the orphans), the notes whose names
    share the rarest words with it. Words are weighted by inverse document
    frequency, so a shared `project_` prefix counts for little and a shared
    `invoice` counts for a lot."""
    targets = graph.orphans() if only is None else only
    if not targets:
        return []
    bags = {n.id: {_stem(t) for t in tokens(norm_key(n.stem) + " " + n.name + " " + " ".join(n.aliases))
                   if not t.isdigit()}
            for n in graph.notes}
    df = Counter(tok for bag in bags.values() for tok in bag)
    total = len(graph.notes)

    def weight(tok: str) -> float:
        return math.log((total + 1) / df[tok])

    out: List[Suggestion] = []
    for o in targets:
        mine = bags[o.id]
        if not mine:
            continue
        scored = []
        for n in graph.notes:
            if n.id == o.id:
                continue
            other = bags[n.id]
            shared = mine & other
            if not shared:
                continue
            union = sum(weight(t) for t in mine | other)
            score = sum(weight(t) for t in shared) / union if union else 0.0
            if score < 0.85:  # near-identical spelling also counts; cheap bounds first
                sm = difflib.SequenceMatcher(None, norm_key(o.name), norm_key(n.name))
                if sm.real_quick_ratio() >= 0.85 and sm.quick_ratio() >= 0.85 and sm.ratio() >= 0.85:
                    score = max(score, sm.ratio())
            if score >= threshold:
                scored.append((score, graph.degree(n.id), n.id))
        scored.sort(key=lambda s: (-s[0], -s[1], s[2]))
        for score, _deg, nid in scored[:top]:
            out.append(Suggestion(o.id, nid, "similar-name", f"{score:.2f}"))
    return out


def dangling_links(graph: Graph) -> List[Dangling]:
    keys = {}
    for n in graph.notes:
        for k in {n.stem, n.name, *n.aliases}:
            keys.setdefault(norm_key(k), n.id)
    choices = list(keys)
    out = []
    for source, target in graph.dangling:
        guess = difflib.get_close_matches(norm_key(target.rsplit("/", 1)[-1]), choices, n=1, cutoff=0.75)
        out.append(Dangling(source, target, keys[guess[0]] if guess else None))
    return out


@dataclass
class Report:
    graph: Graph
    orphans: List[Note]
    dangling: List[Dangling]
    suggestions: List[Suggestion]

    @property
    def stats(self) -> Dict[str, object]:
        g = self.graph
        return {
            "notes": len(g.notes),
            "links": len(g.undirected_edges),
            "orphans": len(self.orphans),
            "dangling": len(self.dangling),
            "suggestions": len(self.suggestions),
            "color_by": g.color_by,
            "groups": {grp: sum(1 for v in g.groups.values() if v == grp) for grp in g.group_order},
        }

    def as_dict(self) -> Dict[str, object]:
        g = self.graph
        return {
            "stats": self.stats,
            "orphans": [n.id for n in self.orphans],
            "dangling": [d.as_dict() for d in self.dangling],
            "suggestions": [s.as_dict() for s in self.suggestions],
            "hubs": [{"id": n.id, "links": g.degree(n.id)} for n in hubs(g)],
        }


def hubs(graph: Graph, top: int = 10) -> List[Note]:
    ranked = sorted((n for n in graph.notes if graph.degree(n.id)),
                    key=lambda n: (-graph.degree(n.id), n.id))
    return ranked[:top]


def build_report(graph: Graph) -> Report:
    orphans = graph.orphans()
    mentions = unlinked_mentions(graph)
    have = {(s.source, s.target) for s in mentions} | {(s.target, s.source) for s in mentions}
    similar = [s for s in similar_names(graph, orphans) if (s.source, s.target) not in have]
    lonely = {n.id for n in orphans}
    # links that would rescue an orphan first, then everything else
    suggestions = sorted(mentions + similar,
                         key=lambda s: (s.source not in lonely and s.target not in lonely,
                                        s.source, s.reason, s.target))
    return Report(graph, orphans, dangling_links(graph), suggestions)


def _label(graph: Graph, note_id: str) -> str:
    n = graph.by_id[note_id]
    return n.id if norm_key(n.name) == norm_key(n.stem) else f"{n.id} ({n.name})"


def _reason_text(s: Suggestion) -> str:
    if s.reason == "mention":
        return f'mentions "{s.detail}"'
    return f"similar name ({s.detail})"


def render_text(report: Report, limit: int = 10) -> str:
    g = report.graph
    lines: List[str] = []

    def section(title: str, rows: List[str]) -> None:
        lines.append("")
        lines.append(title)
        for r in rows[:limit]:
            lines.append("  " + r)
        if len(rows) > limit:
            lines.append(f"  ... {len(rows) - limit} more (full list: --report FILE)")

    section(f"HUBS  most-linked notes", [f"{g.degree(n.id):>3}  {_label(g, n.id)}" for n in hubs(g, limit)])
    section(f"ORPHANS ({len(report.orphans)})  no links in or out",
            [_label(g, n.id) for n in report.orphans] or ["none"])
    section(f"DANGLING LINKS ({len(report.dangling)})  [[target]] matches no note",
            [f"{d.source} -> [[{d.target}]]" + (f'  did you mean "{d.did_you_mean}"?' if d.did_you_mean else "")
             for d in report.dangling] or ["none"])
    section(f"SUGGESTED LINKS ({len(report.suggestions)})",
            [f"{s.source} -> {s.target}  {_reason_text(s)}" for s in report.suggestions] or ["none"])
    return "\n".join(lines)


def render_markdown(report: Report, vault_label: str) -> str:
    g = report.graph
    st = report.stats
    out = [
        f"# Vault report: {vault_label}",
        "",
        f"{st['notes']} notes, {st['links']} links, {st['orphans']} orphans, "
        f"{st['dangling']} dangling links, {st['suggestions']} suggested links. "
        f"Coloured by {st['color_by']}.",
        "",
        "## Groups",
        "",
    ]
    out += [f"- {grp}: {cnt}" for grp, cnt in st["groups"].items()]  # type: ignore[union-attr]
    out += ["", "## Hubs (most links)", ""]
    out += [f"- {g.degree(n.id)} links: `{n.id}`" for n in hubs(g)] or ["- none"]
    out += ["", f"## Orphans ({len(report.orphans)})", "", "Notes with no links in or out.", ""]
    out += [f"- `{n.id}`" for n in report.orphans] or ["- none"]
    out += ["", f"## Dangling links ({len(report.dangling)})", "", "Links whose target matches no note.", ""]
    for d in report.dangling:
        hint = f" (did you mean `{d.did_you_mean}`?)" if d.did_you_mean else ""
        out.append(f"- `{d.source}` links to `[[{d.target}]]`{hint}")
    if not report.dangling:
        out.append("- none")
    out += ["", f"## Suggested links ({len(report.suggestions)})", "",
            "Name matching only. *mentions* = the source note's text contains the target's name "
            "but the two notes are not linked; *similar name* = an orphan whose name shares rare "
            "words with the target.", ""]
    for s in report.suggestions:
        out.append(f"- `{s.source}` -> `[[{g.by_id[s.target].stem}]]`: {_reason_text(s)}")
    if not report.suggestions:
        out.append("- none")
    out.append("")
    return "\n".join(out)

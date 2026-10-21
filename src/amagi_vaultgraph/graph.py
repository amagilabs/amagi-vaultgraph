"""Turn scanned notes into a graph: resolve links, count degree, assign
colour groups, and (for --layered) compute fixed column positions."""
from __future__ import annotations

import math
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .vault import Link, Note

COLOR_MODES = ("auto", "type", "folder", "prefix", "tag")
NO_GROUP = "(none)"
ROOT_GROUP = "(root)"

# Distinct on a near-black background; ordered so the biggest groups get the
# most separable hues. Groups past the end of the list get a hashed colour.
PALETTE = [
    "#4cc9f0", "#f72585", "#ffd166", "#06d6a0", "#b388ff", "#ff8c42",
    "#90e0ef", "#ef476f", "#a7c957", "#f4a261", "#e9c46a", "#80ffdb",
    "#c77dff", "#ff99c8", "#64dfdf", "#fcbf49",
]


def norm_key(text: str) -> str:
    """Case-insensitive, treats spaces, underscores and hyphens as the same."""
    return re.sub(r"[\s_\-]+", " ", text.strip().lower()).strip()


@dataclass
class Graph:
    notes: List[Note]
    edges: Set[Tuple[str, str]]  # directed (source id, target id), no self links
    dangling: List[Tuple[str, str]]  # (source id, raw target) that resolved to nothing
    color_by: str = "folder"
    groups: Dict[str, str] = field(default_factory=dict)  # note id -> group
    colors: Dict[str, str] = field(default_factory=dict)  # group -> hex
    group_order: List[str] = field(default_factory=list)  # biggest first

    def __post_init__(self) -> None:
        self.by_id: Dict[str, Note] = {n.id: n for n in self.notes}
        self.neighbors: Dict[str, Set[str]] = defaultdict(set)
        for a, b in self.edges:
            self.neighbors[a].add(b)
            self.neighbors[b].add(a)

    @property
    def undirected_edges(self) -> List[Tuple[str, str]]:
        return sorted({tuple(sorted(e)) for e in self.edges})  # type: ignore[misc]

    def degree(self, note_id: str) -> int:
        return len(self.neighbors.get(note_id, ()))

    def orphans(self) -> List[Note]:
        return [n for n in self.notes if self.degree(n.id) == 0]


class Resolver:
    """Resolves a link target the way Obsidian does: by path, by file name,
    by frontmatter name or alias. Ties go to the note closest to the source."""

    def __init__(self, notes: List[Note]):
        self.by_path: Dict[str, str] = {}
        self.by_key: Dict[str, List[str]] = defaultdict(list)
        self.folder_of: Dict[str, str] = {}
        for n in notes:
            self.by_path[n.id.lower()] = n.id
            self.folder_of[n.id] = n.folder
            keys = {n.stem, n.name, *n.aliases}
            for k in keys:
                for variant in {k.strip().lower(), norm_key(k)}:
                    if variant and n.id not in self.by_key[variant]:
                        self.by_key[variant].append(n.id)

    def _closest(self, candidates: List[str], source_folder: str) -> str:
        def rank(cid: str) -> Tuple[int, int, str]:
            folder = self.folder_of[cid]
            common = posixpath.commonprefix([folder + "/", source_folder + "/"]).count("/")
            return (-common if folder != source_folder else -999, cid.count("/"), cid)

        return sorted(candidates, key=rank)[0]

    def resolve(self, link: Link, source: Note) -> Optional[str]:
        target = link.target.strip().replace("\\", "/")
        if link.kind == "md":
            base = source.folder if not target.startswith("/") else ""
            joined = posixpath.normpath(posixpath.join(base, target.lstrip("/")))
            joined = joined.rsplit(".", 1)[0].lower()
            hit = self.by_path.get(joined)
            if hit:
                return hit
            target = joined.rsplit("/", 1)[-1]  # fall back to the bare file name
        t = target.strip("/").lower()
        if not t:
            return None
        if "/" in t:
            hit = self.by_path.get(t)
            if hit:
                return hit
            tail = [cid for cid in self.by_path.values() if cid.lower().endswith("/" + t)]
            if tail:
                return self._closest(tail, source.folder)
            t = t.rsplit("/", 1)[-1]
        for key in (t, norm_key(t)):
            cands = self.by_key.get(key)
            if cands:
                return self._closest(cands, source.folder)
        return None


def group_of(note: Note, mode: str) -> str:
    if mode == "type":
        return note.type or NO_GROUP
    if mode == "tag":
        return note.tags[0] if note.tags else NO_GROUP
    if mode == "prefix":
        m = re.match(r"^([^_\-\s.]+)[_\-\s.]", note.stem)
        return m.group(1).lower() if m else ROOT_GROUP
    return note.top_folder or ROOT_GROUP


def pick_color_mode(notes: List[Note]) -> str:
    """`auto`: frontmatter type if most notes have one, else top folder if the
    vault has subfolders, else the file-name prefix (project_x, feedback_y)."""
    if not notes:
        return "folder"
    if sum(1 for n in notes if n.type) * 2 >= len(notes):
        return "type"
    if len({group_of(n, "folder") for n in notes}) > 1:
        return "folder"
    prefixes = Counter(group_of(n, "prefix") for n in notes)
    if 2 <= len(prefixes) <= 24 and prefixes.most_common(1)[0][1] < len(notes):
        return "prefix"
    return "folder"


def _hash_color(name: str) -> str:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    hue = h % 360
    # fixed saturation/lightness, converted from HSL to hex
    s, l = 0.65, 0.62
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][hue // 60]
    return "#{:02x}{:02x}{:02x}".format(*(round((v + m) * 255) for v in (r, g, b)))


def build_graph(notes: List[Note], color_by: str = "auto") -> Graph:
    if color_by not in COLOR_MODES:
        raise ValueError(f"color_by must be one of {', '.join(COLOR_MODES)}")
    resolver = Resolver(notes)
    edges: Set[Tuple[str, str]] = set()
    dangling: List[Tuple[str, str]] = []
    seen_dangling: Set[Tuple[str, str]] = set()
    for n in notes:
        for link in n.links:
            hit = resolver.resolve(link, n)
            if hit is None:
                key = (n.id, link.target)
                if key not in seen_dangling:
                    seen_dangling.add(key)
                    dangling.append(key)
            elif hit != n.id:
                edges.add((n.id, hit))

    mode = pick_color_mode(notes) if color_by == "auto" else color_by
    groups = {n.id: group_of(n, mode) for n in notes}
    sizes = Counter(groups.values())
    order = sorted(sizes, key=lambda g: (g in (NO_GROUP, ROOT_GROUP), -sizes[g], g.lower()))
    colors = {}
    for i, g in enumerate(order):
        if g == NO_GROUP:
            colors[g] = "#6c757d"
        else:
            colors[g] = PALETTE[i] if i < len(PALETTE) else _hash_color(g)
    return Graph(notes, edges, dangling, mode, groups, colors, order)


def layered_positions(graph: Graph, col_gap: float = 100.0, row_gap: float = 16.0,
                      depth_gap: float = 14.0) -> Dict[str, Tuple[float, float, float]]:
    """Columns of notes, one column per colour group (biggest group first),
    best-connected notes at the top. Tall columns wrap into depth so the
    result reads as a row of blocks when you orbit it."""
    total = max(1, len(graph.notes))
    max_rows = max(10, int(math.ceil(math.sqrt(total) * 1.6)))
    members: Dict[str, List[Note]] = defaultdict(list)
    for n in graph.notes:
        members[graph.groups[n.id]].append(n)
    ncols = len(graph.group_order)
    positions: Dict[str, Tuple[float, float, float]] = {}
    for ci, g in enumerate(graph.group_order):
        col = sorted(members[g], key=lambda n: (-graph.degree(n.id), n.name.lower()))
        rows = min(max_rows, len(col))
        layers = int(math.ceil(len(col) / rows)) if rows else 1
        x = (ci - (ncols - 1) / 2) * col_gap
        for i, n in enumerate(col):
            r, d = i % rows, i // rows
            y = ((rows - 1) / 2 - r) * row_gap
            z = (d - (layers - 1) / 2) * depth_gap
            positions[n.id] = (round(x, 2), round(y, 2), round(z, 2))
    return positions

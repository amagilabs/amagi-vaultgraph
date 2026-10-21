"""Read a folder of markdown notes: frontmatter, wikilinks, markdown links.

Only this module touches note text. Everything it hands to the rest of the
package is names, paths and link targets; the body is kept in memory for
unlinked-mention detection and is never written out unless the user asks
for excerpts.
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote

NOTE_EXTENSIONS = (".md", ".markdown")
DEFAULT_SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv"}

_FRONTMATTER_RE = re.compile(
    r"\A(?:\ufeff)?---[ \t]*\r?\n(.*?)(?:\r?\n)?^(?:---|\.\.\.)[ \t]*\r?$\n?",
    re.S | re.M,
)
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[^\n]*$", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_WIKILINK_RE = re.compile(r"!?\[\[([^\[\]\n]+?)\]\]")
_MDLINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\)")
_KEY_RE = re.compile(r"^([A-Za-z_][\w\- ]*):[ \t]*(.*)$")
_LIST_ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(.*)$|^-[ \t]+(.*)$")
_NON_NOTE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp|bmp|pdf|mp3|mp4|webm|mov|wav|ogg|canvas|excalidraw|base)$", re.I)


@dataclass
class Link:
    target: str
    kind: str  # "wiki" or "md"


@dataclass
class Note:
    id: str  # vault-relative posix path without extension, e.g. "projects/lighthouse"
    path: Path
    stem: str
    folder: str  # vault-relative posix folder, "" for the vault root
    name: str  # display name: frontmatter name/title, else the file stem
    aliases: List[str] = field(default_factory=list)
    type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    body: str = ""  # in memory only

    @property
    def top_folder(self) -> str:
        return self.folder.split("/", 1)[0] if self.folder else ""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _inline_list(value: str) -> List[str]:
    inner = value.strip()[1:-1]
    return [_unquote(v) for v in inner.split(",") if _unquote(v)]


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    """Return (frontmatter, body). Handles the YAML subset notes actually use:
    `key: value`, inline `[a, b]` lists, dash lists, and one level of nested
    mappings (Claude Code memory files keep `type` under `metadata:`)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    data: Dict[str, object] = {}
    current_key: Optional[str] = None
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw[:1] in (" ", "\t")
        item = _LIST_ITEM_RE.match(raw)
        if item and current_key is not None:
            value = _unquote(item.group(1) if item.group(1) is not None else item.group(2))
            existing = data.get(current_key)
            if isinstance(existing, dict) and existing:
                continue  # a list nested under a mapping key; not needed
            if not isinstance(existing, list):
                existing = []
                data[current_key] = existing
            if value:
                existing.append(value)
            continue
        km = _KEY_RE.match(raw.strip())
        if not km:
            continue
        key, value = km.group(1).strip().lower(), km.group(2).strip()
        if indented:
            parent = data.get(current_key) if current_key is not None else None
            if isinstance(parent, dict):
                parent[key] = _unquote(value)
            continue  # continuation of a block scalar or deeper nesting
        current_key = key
        if value == "":
            data[key] = {}
        elif value.startswith("[") and value.endswith("]"):
            data[key] = _inline_list(value)
        else:
            data[key] = _unquote(value)
    # an empty mapping that only ever got list items was converted above;
    # an empty mapping with nothing under it means "no value"
    for k, v in list(data.items()):
        if v == {}:
            data[k] = ""
    return data, text[m.end():]


def strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code so example links are ignored."""
    return _INLINE_CODE_RE.sub(" ", _FENCE_RE.sub(" ", text))


def extract_links(text: str) -> List[Link]:
    """All note links in `text`: [[wikilinks]] (with |alias, #heading, ^block)
    and relative markdown links to .md files. Embeds of images/PDFs are skipped."""
    clean = strip_code(text)
    links: List[Link] = []
    for m in _WIKILINK_RE.finditer(clean):
        target = m.group(1).split("|", 1)[0]
        target = re.split(r"[#^]", target, maxsplit=1)[0].strip()
        if not target or _NON_NOTE_EXT_RE.search(target):
            continue
        if target.lower().endswith(".md"):
            target = target[:-3]
        links.append(Link(target, "wiki"))
    for m in _MDLINK_RE.finditer(clean):
        href = unquote(m.group(1).split("#", 1)[0])
        if not href or re.match(r"^[a-z][a-z0-9+.\-]*:", href, re.I):
            continue  # http:, mailto:, obsidian: ...
        if not href.lower().endswith(NOTE_EXTENSIONS):
            continue
        links.append(Link(href, "md"))
    return links


def _as_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _wikilink_text(value: str) -> str:
    """`"[[Some Note]]"` in a property -> `Some Note`; plain text unchanged."""
    m = _WIKILINK_RE.fullmatch(value.strip())
    return m.group(1).split("|")[-1].strip() if m else value


def read_note(path: Path, vault: Path) -> Note:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)
    rel = path.relative_to(vault).as_posix()
    note_id = rel.rsplit(".", 1)[0]
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    stem = path.stem

    name = ""
    for key in ("name", "title"):
        value = fm.get(key)
        if isinstance(value, str) and value.strip():
            name = _wikilink_text(value.strip())
            break

    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    note_type = fm.get("type") or meta.get("type")  # type: ignore[union-attr]
    note_type = str(note_type).strip() if isinstance(note_type, str) and note_type.strip() else None

    aliases = _as_list(fm.get("aliases")) + _as_list(fm.get("alias"))
    tags = [t.lstrip("#") for t in _as_list(fm.get("tags")) + _as_list(fm.get("tag"))]

    return Note(
        id=note_id,
        path=path,
        stem=stem,
        folder=folder,
        name=name or stem,
        aliases=aliases,
        type=note_type,
        tags=tags,
        links=extract_links(text),
        body=strip_code(body),
    )


def _excluded(rel_posix: str, patterns: Iterable[str]) -> bool:
    for pat in patterns:
        pat = pat.strip().rstrip("/")
        if not pat:
            continue
        if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(rel_posix.rsplit("/", 1)[-1], pat):
            return True
        if rel_posix == pat or rel_posix.startswith(pat + "/"):
            return True
    return False


def scan_vault(vault: Path, exclude: Iterable[str] = ()) -> List[Note]:
    """Every markdown note under `vault`, sorted by id. Skips dot-folders
    (.obsidian, .git, .trash), dependency folders, and `exclude` globs."""
    vault = Path(vault)
    patterns = list(exclude)
    notes: List[Note] = []
    for root, dirs, files in os.walk(vault):
        root_path = Path(root)
        rel_root = root_path.relative_to(vault).as_posix()
        rel_root = "" if rel_root == "." else rel_root
        keep = []
        for d in sorted(dirs):
            rel = f"{rel_root}/{d}" if rel_root else d
            if d.startswith(".") or d in DEFAULT_SKIP_DIRS or _excluded(rel, patterns):
                continue
            keep.append(d)
        dirs[:] = keep
        for f in sorted(files):
            if not f.lower().endswith(NOTE_EXTENSIONS) or f.startswith("."):
                continue
            rel = f"{rel_root}/{f}" if rel_root else f
            if _excluded(rel, patterns):
                continue
            notes.append(read_note(root_path / f, vault))
    notes.sort(key=lambda n: n.id.lower())
    return notes

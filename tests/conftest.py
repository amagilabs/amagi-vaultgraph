from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SAMPLE_VAULT = REPO / "examples" / "sample-vault"


@pytest.fixture
def make_vault(tmp_path):
    """make_vault({"a.md": "text", "sub/b.md": "..."}) -> Path of a new vault folder."""

    def _make(files):
        root = tmp_path / "vault"
        root.mkdir(exist_ok=True)
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode("utf-8"))
        return root

    return _make

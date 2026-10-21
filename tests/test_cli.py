import json
import subprocess
import sys
from pathlib import Path

import pytest

from amagi_vaultgraph import __version__
from amagi_vaultgraph.cli import main

SAMPLE_VAULT = Path(__file__).resolve().parents[1] / "examples" / "sample-vault"


def run(args, capsys):
    code = main([str(a) for a in args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_sample_vault_end_to_end(tmp_path, capsys):
    out = tmp_path / "graph.html"
    rep = tmp_path / "report.md"
    js = tmp_path / "graph.json"
    code, stdout, _ = run([SAMPLE_VAULT, "-o", out, "--report", rep, "--json", js], capsys)
    assert code == 0
    assert stdout.splitlines()[0] == ("53 notes, 77 links, 5 orphans, 3 dangling links, "
                                      "10 suggested links (coloured by type, 9 groups)")
    assert "names only" in stdout
    assert 'concepts/retry-with-backoff -> [[rate-limitting]]  did you mean "concepts/rate-limiting"?' in stdout
    assert "inbox/webhook-signing-idea -> concepts/webhooks  similar name" in stdout
    assert 'people/ana-kowalski -> projects/tidepool-api  mentions "Tidepool API"' in stdout

    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "ForceGraph3D" in page
    assert "Quarterly check-ins" not in page  # note text stays out

    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["report"]["stats"]["orphans"] == 5
    assert sorted(data["report"]["orphans"]) == [
        "concepts/semantic-versioning", "inbox/release-versioning-notes", "inbox/untitled-2",
        "inbox/webhook-signing-idea", "reference/regex-snippets",
    ]
    assert len(data["graph"]["nodes"]) == 53 and len(data["graph"]["links"]) == 77
    assert "## Orphans (5)" in rep.read_text(encoding="utf-8")


def test_layered_and_cdn(tmp_path, capsys):
    out = tmp_path / "g.html"
    code, stdout, _ = run([SAMPLE_VAULT, "-o", out, "--layered", "--cdn", "-q"], capsys)
    assert code == 0
    assert "layered, cdn" in stdout
    assert len(stdout.splitlines()) == 2  # summary + "wrote"
    page = out.read_text(encoding="utf-8")
    assert '"layered":true' in page and "cdn.jsdelivr.net" in page


def test_with_excerpts_warns(tmp_path, capsys):
    code, stdout, stderr = run([SAMPLE_VAULT, "-o", tmp_path / "g.html", "--with-excerpts", "-q"], capsys)
    assert code == 0 and "names + excerpts" in stdout and "contains note text" in stderr
    assert "Quarterly check-ins" in (tmp_path / "g.html").read_text(encoding="utf-8")


def test_check_exit_codes(make_vault, tmp_path, capsys):
    clean = make_vault({"a.md": "[[b]]", "b.md": "[[a]]"})
    assert run([clean, "--check", "--no-html", "-q"], capsys)[0] == 0
    assert run([SAMPLE_VAULT, "--check", "--no-html", "-q"], capsys)[0] == 1


def test_no_html_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, stdout, _ = run([SAMPLE_VAULT, "--no-html"], capsys)
    assert code == 0 and "wrote" not in stdout and list(tmp_path.iterdir()) == []


def test_exclude_and_color_by(tmp_path, capsys):
    code, stdout, _ = run([SAMPLE_VAULT, "--no-html", "-q", "--exclude", "daily", "--color-by", "folder"], capsys)
    assert code == 0
    assert stdout.startswith("39 notes,") and "(coloured by folder, 8 groups)" in stdout


def test_bad_input_exit_2(tmp_path, capsys):
    assert run([tmp_path / "missing"], capsys)[0] == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    code, _, err = run([empty], capsys)
    assert code == 2 and "no .md notes" in err
    assert run([SAMPLE_VAULT, "--limit", "-1"], capsys)[0] == 2
    with pytest.raises(SystemExit) as e:
        main([str(SAMPLE_VAULT), "--color-by", "nope"])
    assert e.value.code == 2


def test_module_entry_point_and_version():
    res = subprocess.run([sys.executable, "-m", "amagi_vaultgraph", "--version"], capture_output=True, text=True)
    assert res.returncode == 0 and res.stdout.strip() == f"amagi-vaultgraph {__version__}"

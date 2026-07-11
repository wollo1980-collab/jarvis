"""Tests fuer core/release_scan.py (Welle 4.1) - der Tuersteher vor jeder
Veroeffentlichung. Alle 'Secrets' hier sind erfundene Beispiele.
release-scan: datei-ok (Fixture-Secrets sind der Testgegenstand)."""
from __future__ import annotations

from core.release_scan import Finding, load_local_terms, mask, scan_repo, scan_text


def test_detects_api_key_and_masks_it():
    findings = scan_text("core/x.py", 'key = "sk-abcdefghijklmnopqrstuvwx1234"')

    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert findings[0].kind.startswith("API-Key")
    assert "sk-abcdefghijklmnopqrstuvwx1234" not in findings[0].detail  # maskiert
    assert findings[0].detail.startswith("sk-a")


def test_detects_telegram_token_and_private_key():
    content = (
        "token = '1234567890:AAHdqwerty-abcdefghijklmnopqrstuv1'\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
    )
    kinds = {f.kind for f in scan_text("a.py", content)}
    assert "Telegram-Bot-Token" in kinds
    assert "Privater Schluessel" in kinds


def test_line_pragma_allows_documented_exception():
    line = 'beispiel = "sk-abcdefghijklmnopqrstuvwx1234"  # release-scan: ok (Doku-Beispiel)'
    assert scan_text("a.py", line) == []


def test_file_pragma_skips_whole_file():
    content = '"""release-scan: datei-ok (Beispiele)"""\nkey = "sk-abcdefghijklmnopqrstuvwx1234"\n'
    assert scan_text("tests/test_x.py", content) == []


def test_email_warns_outside_tests_but_not_inside():
    line = "kontakt = 'jemand@firma.de'"
    outside = scan_text("core/x.py", line)
    inside = scan_text("tests/test_x.py", line)

    assert [f.severity for f in outside] == ["WARN"]
    assert inside == []


def test_local_terms_fail_case_insensitive():
    findings = scan_text("docs/x.md", "Der Standard-Ort ist MUSTERHAUSEN.", local_terms=["Musterhausen"])

    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "Musterhausen" not in findings[0].detail  # der Begriff selbst bleibt maskiert


def test_forbidden_tracked_paths_fail(tmp_path):
    findings = scan_repo(
        tmp_path,
        tracked=["config.json", "memory_data/history.json", "logs/x.log", "Voices/x.onnx"],
        local_terms=[],
    )

    assert len(findings) == 4
    assert all(f.severity == "FAIL" for f in findings)
    assert all(f.kind == "Verbotener getrackter Pfad" for f in findings)


def test_clean_repo_passes(tmp_path):
    (tmp_path / "main.py").write_text("print('hallo')\n", encoding="utf-8")

    assert scan_repo(tmp_path, tracked=["main.py"], local_terms=["Musterhausen"]) == []


def test_binary_files_are_skipped(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"\x00\x01sk-abcdefghijklmnopqrstuvwx1234")

    assert scan_repo(tmp_path, tracked=["model.onnx"], local_terms=[]) == []


def test_load_local_terms_ignores_comments_and_blanks(tmp_path):
    (tmp_path / "release_scan_local_terms.txt").write_text(
        "# Kommentar\nMusterhausen\n\n# aus\nZweitbegriff\n", encoding="utf-8"
    )

    assert load_local_terms(tmp_path) == ["Musterhausen", "Zweitbegriff"]


def test_missing_terms_file_returns_empty(tmp_path):
    assert load_local_terms(tmp_path) == []


def test_mask_never_reveals_short_or_long_secrets():
    assert mask("kurz") == "****"
    masked = mask("sk-abcdefghijklmnopqrstuvwx1234")
    assert len(masked) <= 16 and masked.startswith("sk-a")

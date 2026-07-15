

def test_run_git_hides_console_window(monkeypatch, tmp_path):
    """PO-Befund 13.07.: unter der fensterlosen Runtime (pythonw) blitzte beim
    ersten Bau mehrfach ein Terminal auf - jeder git-Aufruf MUSS das
    CREATE_NO_WINDOW-Flag tragen."""
    import subprocess as sp

    import core.project_scaffold as scaffold

    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)

        class R:
            stdout = "ok"
        return R()

    monkeypatch.setattr(scaffold.subprocess, "run", fake_run)
    scaffold._run_git(["status"], tmp_path)

    assert "creationflags" in captured
    assert captured["creationflags"] == getattr(sp, "CREATE_NO_WINDOW", 0)


def test_scaffold_pytest_ini_sets_local_basetemp(tmp_path, monkeypatch):
    """UX-S1 (PO-Live-Befund 13.07.): die Bau-Sandbox sperrt das System-Temp -
    das Geruest muss pytest per --basetemp im Projekt halten, sonst scheitert
    jedes tmp_path-Fixture und der Agent verbrennt sein Zeitlimit."""
    import core.project_scaffold as scaffold

    assert "--basetemp=.pytest_tmp" in scaffold._PYTEST_INI
    assert ".pytest_tmp/" in scaffold._GITIGNORE

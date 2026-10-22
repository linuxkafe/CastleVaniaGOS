"""
Tests for GSN assurance-case generation (T054).
"""

from pathlib import Path


def _find_gsn_script() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "scripts" / "generate-gsn.py"


def test_gsn_script_exists():
    assert _find_gsn_script().exists()


def test_gsn_list():
    import subprocess
    result = subprocess.run(["python3", str(_find_gsn_script()), "--list"],
                           capture_output=True, text=True, cwd=str(_find_gsn_script().parent.parent))
    assert result.returncode == 0
    assert "T023" in result.stdout
    assert "T054" in result.stdout


def test_gsn_generate_t023():
    import subprocess
    result = subprocess.run(["python3", str(_find_gsn_script()), "T023"],
                           capture_output=True, text=True, cwd=str(_find_gsn_script().parent.parent))
    assert result.returncode == 0
    assert "Make `make check` pass" in result.stdout
    assert "digraph GSN" in result.stdout
    assert "goal_T023" in result.stdout
    assert "key_goal" in result.stdout


def test_gsn_generate_unknown_ticket():
    import subprocess
    result = subprocess.run(["python3", str(_find_gsn_script()), "T999"],
                           capture_output=True, text=True, cwd=str(_find_gsn_script().parent.parent))
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_gsn_dot_validate(tmp_path):
    """Validate generated DOT with dot -Tsvg."""
    import subprocess
    out = tmp_path / "test.gsn.dot"
    # Generate for any real ticket
    result = subprocess.run(["python3", str(_find_gsn_script()), "T023", "--output", str(out)],
                           capture_output=True, text=True, cwd=str(_find_gsn_script().parent.parent))
    assert result.returncode == 0
    assert out.exists()

    # Validate with dot
    result = subprocess.run(["dot", "-Tsvg", str(out)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "<svg" in result.stdout


def test_gsn_all_generates():
    """Verify --all generates files without errors."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(["python3", str(_find_gsn_script()), "--all", "--output", tmp],
                               capture_output=True, text=True, cwd=str(_find_gsn_script().parent.parent))
        assert result.returncode == 0
        files = list(Path(tmp).glob("*.gsn.dot"))
        assert len(files) >= 15  # Tickets with verify.md


def test_gsn_generate_t054():
    """T054 should generate its own GSN."""
    import subprocess
    result = subprocess.run(["python3", str(_find_gsn_script()), "T054"],
                           capture_output=True, text=True, cwd=str(_find_gsn_script().parent.parent))
    assert result.returncode == 0
    assert "GSN assurance-case view" in result.stdout or "GSN" in result.stdout
    assert "digraph GSN" in result.stdout

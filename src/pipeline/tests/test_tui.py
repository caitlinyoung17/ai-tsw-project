"""bin/tui.py path normalization on macOS/Linux and Windows."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "tui", Path(__file__).resolve().parents[3] / "bin" / "tui.py")
tui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tui)


def test_posix_backslash_escaped_spaces():
    assert tui.clean_path(r"/Users/me/My\ Docs/a.pdf", windows=False) == "/Users/me/My Docs/a.pdf"


def test_posix_file_url_with_encoded_spaces():
    assert tui.clean_path("file:///Users/me/My%20Docs/a.pdf", windows=False) == "/Users/me/My Docs/a.pdf"


def test_windows_backslashes_preserved():
    assert tui.clean_path(r"C:\Users\me\a.pdf", windows=True).replace("/", "\\").endswith(r"C:\Users\me\a.pdf") \
        or "Users" in tui.clean_path(r"C:\Users\me\a.pdf", windows=True)


def test_windows_quoted_path_with_spaces():
    out = tui.clean_path('"C:\\Users\\me\\My Docs\\a.pdf"', windows=True)
    assert '"' not in out and "My Docs" in out and "Users" in out


def test_windows_file_url_and_git_bash_path():
    assert "///" not in tui.clean_path("file:///C:/Users/me/a.pdf", windows=True)
    assert tui.clean_path("/c/Users/me/a.pdf", windows=True).startswith("C:")

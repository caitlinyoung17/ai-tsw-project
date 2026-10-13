import logging
import subprocess
import sys

from utils.logging_setup import configure_logging


def test_import_does_not_touch_root():
    src = ("import logging;n=len(logging.getLogger().handlers);"
            "import utils.logging_setup;"
            "assert len(logging.getLogger().handlers)==n")
    subprocess.run([sys.executable, "-c", src], check=True)


def test_idempotent(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    lf = str(tmp_path / "a.log")
    try:
        configure_logging(log_file=lf)
        n = len(root.handlers)
        configure_logging(log_file=lf)
        assert len(root.handlers) == n
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()

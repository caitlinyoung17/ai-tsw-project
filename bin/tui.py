#!/usr/bin/env python3
"""Interactive prompt for the TSW pipeline. Stdlib only; launched by ./run.sh."""
import os
import shlex
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
ROOT = BIN.parent
RUN_PIPELINE = BIN / "run_pipeline.sh"
STEPS = [
    ("1", "Extract metadata from dissertation text files"),
    ("1.5", "Reprocess failed or incomplete batch extractions"),
    ("2", "Enhance subject terms with standard vocabulary lookups"),
    ("3", "Select the best vocabulary term for each subject"),
    ("4", "Build entity authority records"),
]


def clean_path(raw: str) -> str:
    """Normalize a pasted or drag-and-dropped path (quotes, backslash escapes, file://)."""
    raw = raw.strip()
    if raw.startswith("file://"):
        raw = raw[len("file://"):]
    try:
        parts = shlex.split(raw)
        if len(parts) == 1:
            raw = parts[0]
    except ValueError:
        pass
    return str(Path(raw).expanduser())


def ask(prompt, default=None):
    suffix = f" [{default}]" if default not in (None, "") else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        sys.exit(1)
    return val or (default or "")


def ask_yes_no(prompt, default=False):
    d = "Y/n" if default else "y/N"
    val = ask(f"{prompt} ({d})").lower()
    return default if not val else val.startswith("y")


def ask_choice(prompt, options):
    print(prompt)
    for i, label in enumerate(options, 1):
        print(f"  {i}. {label}")
    while True:
        val = ask("Choose a number", "1")
        if val.isdigit() and 1 <= int(val) <= len(options):
            return int(val) - 1
        print("  Please enter one of the listed numbers.")


def ask_path(prompt, want_dir=None):
    print(f"{prompt}\n  (drag and drop it into this window, or paste the path, then press Enter)")
    while True:
        p = clean_path(ask(">"))
        path = Path(p)
        if not p or not path.exists():
            print("  That path doesn't exist. Try again.")
        elif want_dir is True and not path.is_dir():
            print("  Please provide a folder.")
        else:
            return str(path)


def ask_int(prompt):
    while True:
        val = ask(prompt, "")
        if not val:
            return None
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("  Enter a positive whole number, or leave blank for the default.")


def main():
    print("\n=== TSW Pipeline ===\n")
    mode = ask_choice("What would you like to do?", [
        "Process a PDF or .txt file",
        "Process a folder of PDFs / .txt files",
        "Resume an existing run folder",
    ])
    args = []
    if mode == 2:
        target = ask_path("Run folder to resume:", want_dir=True)
        args += ["--folder", target]
    else:
        target = ask_path("File to process:" if mode == 0 else "Folder to process:",
                          want_dir=(mode == 1))
        args = [target]

    print("\nSteps to run (default: all).")
    for sid, label in STEPS:
        print(f"  {sid}: {label}")
    default_steps = "2,3,4" if mode == 2 else "1,1.5,2,3,4"
    steps = ask("Comma-separated steps", default_steps).replace(" ", "")
    args += ["--steps", steps]

    model = ask("\nModel override (blank for default)")
    if model:
        args += ["--model", model]

    batch = ask_choice("\nBatch API mode:", ["Auto (default)", "Force batch", "No batch"])
    if batch == 1:
        args.append("--batch")
    elif batch == 2:
        args.append("--no-batch")

    if ask_yes_no("\nScan the full text in chunks?", False):
        args.append("--full-text-scan")
        for flag, label in (("--chunk-size", "Chunk size"),
                            ("--max-chunks", "Max chunks")):
            n = ask_int(f"{label} (blank for default)")
            if n:
                args += [flag, str(n)]
    else:
        n = ask_int("Abstract scan max chunks (blank for default)")
        if n:
            args += ["--abstract-scan-max-chunks", str(n)]

    if ask_yes_no("Keep going if a step fails?", False):
        args.append("--keep-going")

    cmd = [str(RUN_PIPELINE), *args]
    print("\nAbout to run:\n  " + " ".join(shlex.quote(c) for c in cmd))
    print("This calls the LLM provider and may incur cost.")
    if not ask_yes_no("Proceed?", True):
        print("Cancelled.")
        return 0
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)

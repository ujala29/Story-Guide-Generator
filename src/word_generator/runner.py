# src/word_generator/runner.py
#
# Entry point for Word document generation.
# Step 1: generate_reference_docx.py  -> output/reference.docx  (style template)
# Step 2: generate_word_doc.py        -> output/<dashboard>_story_guide.docx
#
# Usage:
#   python runner.py                      # risk-dash
#   python runner.py --dashboard pac-dash

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import argparse
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent

STEPS = [
    ("reference_docx", "generate_reference_docx.py", []),
    ("word_doc",        "generate_word_doc.py",       ["--dashboard"]),
]


def run_step(label: str, script: str, extra_args: list[str]) -> None:
    cmd = [sys.executable, str(HERE / script)] + extra_args
    print(f"\n  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=False, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"\n[runner] TIMEOUT — {script} did not finish within 5 minutes")
        sys.exit(1)
    if result.returncode != 0:
        print(f"\n[runner] FAILED — {script} exited with code {result.returncode}")
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Word Document Generator")
    parser.add_argument(
        "--dashboard", default="risk-dash",
        help="Dashboard name (default: risk-dash)"
    )
    args = parser.parse_args()

    print("=" * 62)
    print("  Word Generator")
    print(f"  Dashboard : {args.dashboard}")
    print("=" * 62)

    print("\n[step 1] Generate reference.docx (style template)")
    print("-" * 62)
    run_step("reference_docx", "generate_reference_docx.py", [])

    print("\n[step 2] Generate story guide Word document")
    print("-" * 62)
    run_step("word_doc", "generate_word_doc.py", ["--dashboard", args.dashboard])

    print("\n" + "=" * 62)
    print("  COMPLETE")
    print(f"  Output -> output/{args.dashboard}_story_guide.docx")
    print("=" * 62)


if __name__ == "__main__":
    main()

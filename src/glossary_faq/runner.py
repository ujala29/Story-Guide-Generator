"""
Glossary & FAQ runner
=====================
Runs both generators sequentially (they are independent but share the same
stage3 inputs, so sequential is fine — no parallel needed).

Usage
-----
  python runner.py                   # risk-dash, both
  python runner.py --dashboard pac-dash
  python runner.py --skip-glossary   # FAQ only
  python runner.py --skip-faq        # Glossary only
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _run(label: str, script: str, extra_args: list[str]) -> int:
    cmd = [sys.executable, str(HERE / script)] + extra_args
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False, cwd=str(HERE))
    if result.returncode != 0:
        print(f"\n[runner] FAILED — {script} exited with code {result.returncode}")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Glossary and FAQ generators"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    parser.add_argument("--skip-glossary", action="store_true",
                        help="Skip glossary_generator.py")
    parser.add_argument("--skip-faq", action="store_true",
                        help="Skip faq_generator.py")
    args = parser.parse_args()

    dash_args = ["--dashboard", args.dashboard]

    print("=" * 55)
    print(f"  Glossary & FAQ runner — dashboard: {args.dashboard}")
    print("=" * 55)

    if not args.skip_glossary:
        print("\n[glossary] Building glossary...")
        print("-" * 55)
        rc = _run("glossary", "glossary_generator.py", dash_args)
        if rc != 0:
            sys.exit(rc)

    if not args.skip_faq:
        print("\n[faq] Building FAQ...")
        print("-" * 55)
        rc = _run("faq", "faq_generator.py", dash_args)
        if rc != 0:
            sys.exit(rc)

    print("\n" + "=" * 55)
    print("  DONE")
    print(f"  Output → output/dashboards/{args.dashboard}/stage3/")
    print(f"    glossary.md")
    print(f"    faq.md")
    print("=" * 55)


if __name__ == "__main__":
    main()

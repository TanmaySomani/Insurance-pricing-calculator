"""Run from any directory with an explicit --root, or from the repository root."""

import argparse
from pathlib import Path

from insurance_pricing.download import download


def main() -> None:
    parser = argparse.ArgumentParser(description="Insurance pricing project pipeline")
    parser.add_argument("command", choices=["download", "prepare"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "pyproject.toml").exists():
        parser.error("--root must point to the project repository")
    if args.command == "download":
        download(root)
    else:
        from insurance_pricing.data import prepare

        prepare(root)


if __name__ == "__main__":
    main()

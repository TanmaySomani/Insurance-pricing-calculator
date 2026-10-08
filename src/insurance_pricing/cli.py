"""Run from any directory with an explicit --root, or from the repository root."""

import argparse
from pathlib import Path

from insurance_pricing.download import download


def main() -> None:
    parser = argparse.ArgumentParser(description="Insurance pricing project pipeline")
    parser.add_argument("command", choices=["download", "prepare", "train-glm", "train-boost", "evaluate"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "pyproject.toml").exists():
        parser.error("--root must point to the project repository")
    if args.command == "download":
        download(root)
    elif args.command == "prepare":
        from insurance_pricing.data import prepare

        prepare(root)
    elif args.command == "train-glm":
        from insurance_pricing.training import train_glm

        train_glm(root)
    else:
        from insurance_pricing.comparison import evaluate_models, train_boost

        (train_boost if args.command == "train-boost" else evaluate_models)(root)


if __name__ == "__main__":
    main()

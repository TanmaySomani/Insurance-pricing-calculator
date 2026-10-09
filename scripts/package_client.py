"""Package an allowlisted repository demo; never include data or model records."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("src", "configs", "reports", "docs", "figures", "tests", "scripts", ".streamlit", "output/pdf")
FILES = ("README.md", "CHECKPOINT.md", "app.py", "pyproject.toml", "requirements.txt", "requirements.lock.txt", "requirements-report.txt", ".gitignore")
SUFFIXES = {".py", ".json", ".csv", ".md", ".png", ".jpg", ".pdf", ".toml", ".txt"}


def client_files(root=ROOT):
    paths = [root / name for name in FILES]
    for name in DIRECTORIES:
        paths += [p for p in (root / name).rglob("*") if p.is_file() and p.suffix in SUFFIXES and "__pycache__" not in p.parts]
    result = sorted(set(paths), key=lambda p: p.relative_to(root).as_posix())
    for path in result:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Unsafe or missing package file: {path}")
    return result


def package(root=ROOT):
    files = client_files(root)
    manifest = {"purpose": "Aggregate demo and client handover; no policy data or fitted models",
                "files_sha256": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    destination = root / "dist"; destination.mkdir(exist_ok=True)
    output = destination / "insurance-pricing-client.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in [(p.relative_to(root).as_posix(), p.read_bytes()) for p in files] + [("CLIENT_PACKAGE_MANIFEST.json", (json.dumps(manifest, indent=2) + "\n").encode())]:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest["files_sha256"]) | {"CLIENT_PACKAGE_MANIFEST.json"}
        for name, digest in manifest["files_sha256"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    record = {"archive": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "files": len(files), "bytes": output.stat().st_size}
    output.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return output


if __name__ == "__main__":
    package()

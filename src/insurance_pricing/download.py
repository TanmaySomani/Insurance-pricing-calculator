"""Download immutable OpenML dataset versions and record verifiable provenance."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = {"frequency": (41214, "freMTPL2freq"), "severity": (41215, "freMTPL2sev")}


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(root: Path) -> dict:
    """Use the cache only if its bytes match the repository's source lock.

    The OpenML MD5 refers to ARFF; it must not be applied to the Parquet mirror.
    Our SHA-256 lock verifies the exact Parquet snapshot used by this project.
    """
    raw = root / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    lock_path = root / "configs/source_lock.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    manifest = {}
    for kind, (dataset_id, name) in SOURCES.items():
        path = raw / f"{name}.parquet"
        metadata_url = f"https://www.openml.org/api/v1/json/data/{dataset_id}"
        url = f"https://data.openml.org/datasets/0004/{dataset_id}/dataset_{dataset_id}.pq"
        metadata_path = raw / f"{name}.metadata.json"
        if not path.exists() or not metadata_path.exists():
            with urlopen(Request(metadata_url, headers={"User-Agent": "InsurancePricingResearch/0.1"}), timeout=90) as response:
                metadata = json.load(response)["data_set_description"]
            if metadata["name"] != name or str(metadata["version"]) != "1":
                raise ValueError(f"Unexpected OpenML version for {name}")
            if metadata.get("parquet_url") != url:
                raise ValueError(f"Unexpected download location for {name}")
            temporary = path.with_suffix(".part")
            try:
                with urlopen(Request(url, headers={"User-Agent": "InsurancePricingResearch/0.1"}), timeout=90) as response, temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
                digest = sha256(temporary)
                if kind in lock and digest != lock[kind]["sha256"]:
                    raise ValueError(f"Source bytes changed for {name}; inspect before updating the lock")
                temporary.replace(path)
                metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
            finally:
                temporary.unlink(missing_ok=True)
        metadata = json.loads(metadata_path.read_text())
        digest = sha256(path)
        if metadata["name"] != name or str(metadata["version"]) != "1":
            raise ValueError(f"Unexpected cached metadata for {name}")
        if kind in lock and digest != lock[kind]["sha256"]:
            raise ValueError(f"Cache checksum mismatch for {name}; remove the corrupted cache and download again")
        manifest[kind] = {
            "dataset_id": dataset_id, "name": name, "version": 1,
            "licence_reported_by_openml": metadata.get("licence"),
            "metadata_url": metadata_url, "download_url": url,
            "sha256": digest, "bytes": path.stat().st_size,
            "citation": metadata.get("citation"),
        }
        print(f"Verified {name}: {path.stat().st_size:,} bytes", flush=True)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

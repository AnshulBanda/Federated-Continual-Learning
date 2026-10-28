"""Restore a verified manifest's line endings in an isolated runtime view.

The Windows-produced reference artifacts hash CRLF bytes. Git checkouts on
macOS may contain LF bytes for the same JSON. Never replace a recorded hash or
relax the engine's byte-for-byte input verification.
"""
import hashlib
import json
from pathlib import Path


def verified_dataset_view(dataset: Path, preprocessing: Path, staging: Path) -> Path:
    manifest = Path("configuration/model_feature_columns.json")
    artifact = json.loads(preprocessing.read_text(encoding="utf-8"))
    expected = {digest for bank in artifact["banks"].values()
                for name, digest in bank["input_sha256"].items()
                if name.replace("\\", "/") == manifest.as_posix()}
    original = (dataset / manifest).read_bytes()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if expected == {digest(original)}:
        return dataset
    lf = original.replace(b"\r\n", b"\n")
    restored = next((data for data in (lf, lf.replace(b"\n", b"\r\n"))
                     if expected == {digest(data)}), None)
    if restored is None:
        raise ValueError("feature manifest differs from verified preprocessing; line-ending restoration cannot reproduce its exact hash")
    view = staging / "verified_dataset"
    view.mkdir()
    for entry in dataset.iterdir():
        if entry.name != "configuration":
            (view / entry.name).symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
    (view / "configuration").mkdir()
    for entry in (dataset / "configuration").iterdir():
        if entry.name != manifest.name:
            (view / "configuration" / entry.name).symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
    (view / manifest).write_bytes(restored)
    return view

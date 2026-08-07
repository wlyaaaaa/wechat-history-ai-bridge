#!/usr/bin/env python3
"""Build a read-only, account-scoped integrity manifest for a private snapshot.

The tool never parses WeChat databases or media. It enumerates files, hashes raw
bytes, then performs a complete second-pass readback before publishing a receipt.
Outputs belong in a private, non-repository destination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = "weflowbridge.private-snapshot-manifest.v1"
RECEIPT_SCHEMA = "weflowbridge.private-snapshot-readback-receipt.v1"
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SnapshotManifestError(RuntimeError):
    """Raised when a private snapshot cannot be verified safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _has_reparse_point(stat_result: os.stat_result) -> bool:
    return bool(getattr(stat_result, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        directory_stat = directory.stat(follow_symlinks=False)
        if directory.is_symlink() or _has_reparse_point(directory_stat):
            raise SnapshotManifestError(f"reparse point is not allowed: {directory}")
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            entry_path = Path(entry.path)
            stat_result = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or _has_reparse_point(stat_result):
                raise SnapshotManifestError(f"reparse point is not allowed: {entry_path}")
            if entry.is_dir(follow_symlinks=False):
                pending.append(entry_path)
            elif entry.is_file(follow_symlinks=False):
                files.append(entry_path)
            else:
                raise SnapshotManifestError(f"unsupported filesystem object: {entry_path}")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical_json(value) + b"\n")
    os.replace(temporary, path)


def _write_progress(
    path: Path,
    *,
    phase: str,
    completed_files: int,
    completed_bytes: int,
    total_files: int,
    total_bytes: int,
) -> None:
    _write_json(
        path,
        {
            "schema": "weflowbridge.private-snapshot-progress.v1",
            "phase": phase,
            "completed_files": completed_files,
            "completed_bytes": completed_bytes,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "updated_at_utc": _utc_now(),
        },
    )


def _stat_identity(path: Path) -> tuple[int, int]:
    stat_result = path.stat(follow_symlinks=False)
    if path.is_symlink() or _has_reparse_point(stat_result):
        raise SnapshotManifestError(f"reparse point is not allowed: {path}")
    return stat_result.st_size, stat_result.st_mtime_ns


def build_manifest(
    source_root: Path,
    destination: Path,
    source_instance_id: str,
    *,
    progress_interval_files: int = 1000,
) -> dict[str, object]:
    source_root = source_root.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if not source_root.is_dir():
        raise SnapshotManifestError("source root must be a directory")
    if not source_instance_id.strip():
        raise SnapshotManifestError("source instance id must not be empty")
    if _is_within(destination, REPOSITORY_ROOT):
        raise SnapshotManifestError("destination must be outside the repository tree")
    if destination.exists():
        raise SnapshotManifestError("destination already exists")
    if _is_within(destination, source_root) or _is_within(source_root, destination):
        raise SnapshotManifestError("source and destination must not contain each other")

    destination.parent.mkdir(parents=True, exist_ok=True)
    incomplete = destination.with_name(f"{destination.name}.incomplete")
    if incomplete.exists():
        raise SnapshotManifestError("incomplete destination already exists")
    incomplete.mkdir()

    progress_path = incomplete / "progress.json"
    files_path = incomplete / "files.jsonl"
    manifest_path = incomplete / "manifest.json"
    receipt_path = incomplete / "readback-receipt.json"

    files = _collect_files(source_root)
    if not files:
        raise SnapshotManifestError("empty source snapshot is not acceptable")
    initial_identities = [_stat_identity(path) for path in files]
    total_files = len(files)
    total_bytes = sum(size for size, _ in initial_identities)
    _write_progress(
        progress_path,
        phase="hashing",
        completed_files=0,
        completed_bytes=0,
        total_files=total_files,
        total_bytes=total_bytes,
    )

    snapshot_digest = hashlib.sha256()
    hashed_bytes = 0
    with files_path.open("wb") as output:
        for index, (path, (expected_size, expected_mtime_ns)) in enumerate(
            zip(files, initial_identities), start=1
        ):
            digest, observed_bytes = _sha256_file(path)
            final_size, final_mtime_ns = _stat_identity(path)
            if (
                observed_bytes != expected_size
                or final_size != expected_size
                or final_mtime_ns != expected_mtime_ns
            ):
                raise SnapshotManifestError(
                    f"source changed while hashing: {path.relative_to(source_root).as_posix()}"
                )
            record = {
                "relative_path": path.relative_to(source_root).as_posix(),
                "size_bytes": expected_size,
                "mtime_ns": expected_mtime_ns,
                "sha256": digest,
            }
            line = _canonical_json(record) + b"\n"
            output.write(line)
            snapshot_digest.update(line)
            hashed_bytes += expected_size
            if index % max(1, progress_interval_files) == 0 or index == total_files:
                _write_progress(
                    progress_path,
                    phase="hashing",
                    completed_files=index,
                    completed_bytes=hashed_bytes,
                    total_files=total_files,
                    total_bytes=total_bytes,
                )

    manifest = {
        "schema": SCHEMA,
        "source_instance_id": source_instance_id,
        "source_root": str(source_root),
        "payload_mode": "external_read_only_reference",
        "hash_algorithm": "sha256",
        "file_count": total_files,
        "total_bytes": total_bytes,
        "snapshot_fingerprint": snapshot_digest.hexdigest(),
        "files_manifest": "files.jsonl",
        "created_at_utc": _utc_now(),
    }
    _write_json(manifest_path, manifest)

    current_files = _collect_files(source_root)
    expected_paths = [path.relative_to(source_root).as_posix() for path in files]
    current_paths = [path.relative_to(source_root).as_posix() for path in current_files]
    if current_paths != expected_paths:
        raise SnapshotManifestError("source file set changed before readback")

    _write_progress(
        progress_path,
        phase="readback",
        completed_files=0,
        completed_bytes=0,
        total_files=total_files,
        total_bytes=total_bytes,
    )
    readback_bytes = 0
    with files_path.open("r", encoding="utf-8") as records:
        for index, (path, line) in enumerate(zip(current_files, records, strict=True), start=1):
            record = json.loads(line)
            relative_path = path.relative_to(source_root).as_posix()
            if record["relative_path"] != relative_path:
                raise SnapshotManifestError("manifest order changed before readback")
            size, mtime_ns = _stat_identity(path)
            digest, observed_bytes = _sha256_file(path)
            final_size, final_mtime_ns = _stat_identity(path)
            if (
                size != record["size_bytes"]
                or observed_bytes != record["size_bytes"]
                or final_size != record["size_bytes"]
                or mtime_ns != record["mtime_ns"]
                or final_mtime_ns != record["mtime_ns"]
                or digest != record["sha256"]
            ):
                raise SnapshotManifestError(f"readback mismatch: {relative_path}")
            readback_bytes += observed_bytes
            if index % max(1, progress_interval_files) == 0 or index == total_files:
                _write_progress(
                    progress_path,
                    phase="readback",
                    completed_files=index,
                    completed_bytes=readback_bytes,
                    total_files=total_files,
                    total_bytes=total_bytes,
                )

    final_files = _collect_files(source_root)
    final_paths = [path.relative_to(source_root).as_posix() for path in final_files]
    final_identities = [_stat_identity(path) for path in final_files]
    if final_paths != expected_paths or final_identities != initial_identities:
        raise SnapshotManifestError("source changed after readback")

    files_manifest_sha256, _ = _sha256_file(files_path)
    manifest_sha256, _ = _sha256_file(manifest_path)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "verified",
        "source_instance_id": source_instance_id,
        "payload_mode": "external_read_only_reference",
        "verification": "full_sha256_second_pass",
        "file_count": total_files,
        "total_bytes": total_bytes,
        "snapshot_fingerprint": snapshot_digest.hexdigest(),
        "files_manifest_sha256": files_manifest_sha256,
        "manifest_sha256": manifest_sha256,
        "verified_at_utc": _utc_now(),
    }
    _write_json(receipt_path, receipt)
    _write_progress(
        progress_path,
        phase="verified",
        completed_files=total_files,
        completed_bytes=total_bytes,
        total_files=total_files,
        total_bytes=total_bytes,
    )
    incomplete.rename(destination)
    return receipt


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--source-instance-id", required=True)
    parser.add_argument("--progress-interval-files", type=int, default=1000)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = build_manifest(
            args.source_root,
            args.destination,
            args.source_instance_id,
            progress_interval_files=args.progress_interval_files,
        )
    except (OSError, SnapshotManifestError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

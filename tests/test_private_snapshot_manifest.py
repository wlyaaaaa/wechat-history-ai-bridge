import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "build_private_snapshot_manifest.py"
SPEC = importlib.util.spec_from_file_location("private_snapshot_manifest", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrivateSnapshotManifestTests(unittest.TestCase):
    def test_builds_account_scoped_manifest_and_full_readback_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "output" / "snapshot"
            (source / "msg").mkdir(parents=True)
            (source / "media").mkdir()
            (source / "msg" / "main.db").write_bytes(b"synthetic-database-bytes")
            (source / "media" / "image.bin").write_bytes(b"synthetic-media-bytes")

            receipt = MODULE.build_manifest(
                source,
                destination,
                "src.weflow.account.synthetic",
                progress_interval_files=1,
            )

            self.assertEqual(receipt["status"], "verified")
            self.assertEqual(receipt["file_count"], 2)
            self.assertEqual(
                receipt["total_bytes"],
                len(b"synthetic-database-bytes") + len(b"synthetic-media-bytes"),
            )
            self.assertFalse(destination.with_name("snapshot.incomplete").exists())
            manifest = json.loads((destination / "manifest.json").read_text("utf-8"))
            persisted_receipt = json.loads(
                (destination / "readback-receipt.json").read_text("utf-8")
            )
            records = [
                json.loads(line)
                for line in (destination / "files.jsonl").read_text("utf-8").splitlines()
            ]
            self.assertEqual(manifest["source_instance_id"], "src.weflow.account.synthetic")
            self.assertEqual(manifest["payload_mode"], "external_read_only_reference")
            self.assertEqual(persisted_receipt, receipt)
            self.assertEqual(
                [record["relative_path"] for record in records],
                ["media/image.bin", "msg/main.db"],
            )
            output_text = (destination / "files.jsonl").read_text("utf-8")
            self.assertNotIn("synthetic-database-bytes", output_text)
            self.assertNotIn("synthetic-media-bytes", output_text)

    def test_rejects_destination_inside_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            (source / "a.bin").write_bytes(b"a")

            with self.assertRaisesRegex(
                MODULE.SnapshotManifestError, "must not contain each other"
            ):
                MODULE.build_manifest(
                    source,
                    source / "manifest",
                    "src.weflow.account.synthetic",
                )

    def test_rejects_existing_destination_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "snapshot"
            source.mkdir()
            destination.mkdir()
            marker = destination / "preserve.txt"
            marker.write_text("preserve", encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.SnapshotManifestError, "destination already exists"
            ):
                MODULE.build_manifest(
                    source,
                    destination,
                    "src.weflow.account.synthetic",
                )
            self.assertEqual(marker.read_text("utf-8"), "preserve")

    def test_rejects_empty_source_as_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()

            with self.assertRaisesRegex(
                MODULE.SnapshotManifestError, "empty source snapshot"
            ):
                MODULE.build_manifest(
                    source,
                    root / "snapshot",
                    "src.weflow.account.synthetic",
                )


if __name__ == "__main__":
    unittest.main()

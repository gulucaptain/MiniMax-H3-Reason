"""Contract tests for completeness, path confinement and submission identity."""
import json
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdk.interface import VERSION, load_cases, resolve_asset, validate_submission


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.case = {"id": "VDR-001", "scenario": "VDR",
                     "inputs": {"video": {"path": "input.mp4", "duration_s": 2}},
                     "output_spec": {"allowed_layouts": ["continuation_only", "with_prefix"]}}
        (self.root / "data/cases.jsonl").write_text(json.dumps(self.case) + "\n")
        (self.root / "data/dataset.json").write_text(json.dumps({"manifest_sha256": "test"}))
        (self.root / "submission.json").write_text(json.dumps({
            "schema_version": VERSION, "dataset_manifest_sha256": "test", "scope": ["VDR"],
            "model_id": "model", "model_version": "1", "adapter_version": "1"}))
        (self.root / "out.mp4").write_bytes(b"placeholder")
        self.record = {"id": "VDR-001", "status": "ok", "output": {
            "kind": "video", "path": "out.mp4", "layout": "continuation_only",
            "evaluation_start_s": 0, "evaluation_end_s": None}}

    def check(self, rows):
        submission = self.root / "outputs.jsonl"
        submission.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return validate_submission(self.root, submission)

    def test_valid_structure(self):
        self.assertTrue(self.check([self.record])["valid"])

    def test_missing_ids_are_not_silently_excluded(self):
        self.assertEqual(self.check([])["missing_ids"], ["VDR-001"])

    def test_duplicate_rejected(self):
        self.assertFalse(self.check([self.record, self.record])["valid"])

    def test_unknown_id_rejected(self):
        self.record["id"] = "VDR-999"
        self.assertFalse(self.check([self.record])["valid"])

    def test_path_escape_rejected(self):
        for path in ("../outside.mp4", "/tmp/outside.mp4"):
            with self.assertRaises(ValueError):
                resolve_asset(self.root, path)

    def test_symlink_escape_rejected(self):
        (self.root / "link").symlink_to(self.root.parent)
        with self.assertRaises(ValueError):
            resolve_asset(self.root, "link/outside.mp4")

    def test_unsupported_requires_reason(self):
        self.assertFalse(self.check([{"id": "VDR-001", "status": "unsupported", "output": None}])["valid"])
        self.assertTrue(self.check([{"id": "VDR-001", "status": "unsupported", "reason": "no video", "output": None}])["valid"])

    def test_invalid_interval_rejected(self):
        for start in (True, -1, float("nan"), float("inf")):
            self.record["output"]["evaluation_start_s"] = start
            self.assertFalse(self.check([self.record])["valid"])

    def test_layout_rejected(self):
        self.record["output"]["layout"] = "annotated_full_video"
        self.assertFalse(self.check([self.record])["valid"])

    def test_dataset_identity_rejected(self):
        meta = json.loads((self.root / "submission.json").read_text())
        meta["dataset_manifest_sha256"] = "another"
        (self.root / "submission.json").write_text(json.dumps(meta))
        with self.assertRaises(ValueError):
            self.check([])

    def test_loader_does_not_read_references(self):
        (self.root / "data/evaluation").mkdir()
        (self.root / "data/evaluation/references.jsonl").write_text("not valid JSON")
        requests = list(load_cases(self.root))
        self.assertEqual(len(requests), 1)
        self.assertNotIn("plausible_outcomes", requests[0])
        self.assertEqual(requests[0]["inputs"]["video"]["local_path"], str((self.root / "input.mp4").resolve()))


if __name__ == "__main__":
    unittest.main()

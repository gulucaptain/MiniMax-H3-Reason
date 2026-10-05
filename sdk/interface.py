"""Model-independent benchmark loader and submission validator (standard library)."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
from typing import Protocol

VERSION = "0.1.0"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{number}: expected object")
            rows.append(row)
    return rows


def resolve_asset(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Asset path must be a nonempty relative path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Asset path escapes its root")
    return path


def load_cases(dataset_root: str | Path, scenarios: set[str] | None = None):
    """Yield inference requests only; references are never loaded."""
    root = Path(dataset_root).resolve()
    for case in read_jsonl(root / "data/cases.jsonl"):
        if scenarios is not None and case["scenario"] not in scenarios:
            continue
        request = dict(case)
        request["inputs"] = {
            kind: ({**asset, "local_path": str(resolve_asset(root, asset["path"]))}
                   if asset is not None else None)
            for kind, asset in case["inputs"].items()
        }
        yield request


class ModelAdapter(Protocol):
    """Implement locally for any provider. Return one submission record per case.

    Adapter-owned preprocessing must be documented in submission metadata.
    Do not pass evaluator references or audio captions into generate().
    """

    def generate(self, request: dict, output_root: Path) -> dict: ...


def validate_submission(dataset_root: Path, submission: Path, probe: bool = False) -> dict:
    dataset = json.loads((dataset_root / "data/dataset.json").read_text())
    cases = {r["id"]: r for r in read_jsonl(dataset_root / "data/cases.jsonl")}
    metadata = json.loads((submission.parent / "submission.json").read_text())
    if metadata.get("schema_version") != VERSION:
        raise ValueError("Unsupported submission schema_version")
    if metadata.get("dataset_manifest_sha256") != dataset["manifest_sha256"]:
        raise ValueError("Submission targets a different dataset manifest")
    scope = metadata.get("scope")
    if not isinstance(scope, list) or not scope or len(set(scope)) != len(scope):
        raise ValueError("scope must contain unique scenario names")
    if not set(scope) <= {r["scenario"] for r in cases.values()}:
        raise ValueError("Unknown scenario in scope")
    for key in ("model_id", "model_version", "adapter_version"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError(f"Missing metadata: {key}")
    seen, counts, errors = set(), {}, []
    for row in read_jsonl(submission):
        cid = row.get("id")
        try:
            if not isinstance(cid, str) or cid not in cases:
                raise ValueError("Unknown case ID")
            if cid in seen:
                raise ValueError("Duplicate case ID")
            seen.add(cid)
            case = cases[cid]
            if case["scenario"] not in scope:
                raise ValueError("Case is outside declared scope")
            status = row.get("status")
            if status not in {"ok", "error", "unsupported", "skipped"}:
                raise ValueError("Invalid status")
            if status != "ok":
                if not isinstance(row.get("reason"), str) or not row["reason"].strip():
                    raise ValueError("Non-ok result requires reason")
                if row.get("output") is not None:
                    raise ValueError("Non-ok result must have null output")
            else:
                out = row.get("output")
                if not isinstance(out, dict) or out.get("kind") != "video":
                    raise ValueError("This track requires a video output")
                path = resolve_asset(submission.parent, out.get("path"))
                if not path.is_file():
                    raise ValueError("Output file is missing")
                allowed = case["output_spec"]["allowed_layouts"]
                if out.get("layout") not in allowed:
                    raise ValueError(f"layout must be one of {allowed}")
                start, end = out.get("evaluation_start_s"), out.get("evaluation_end_s")
                if (isinstance(start, bool) or not isinstance(start, (int, float))
                        or not math.isfinite(start) or start < 0):
                    raise ValueError("evaluation_start_s must be finite and >= 0")
                if end is not None and (isinstance(end, bool) or not isinstance(end, (int, float))
                                        or not math.isfinite(end) or end <= start):
                    raise ValueError("evaluation_end_s must exceed start or be null")
                if out["layout"] != "with_prefix" and start != 0:
                    raise ValueError("Non-prefix output must start at 0")
                if probe:
                    info = json.loads(subprocess.check_output([
                        "ffprobe", "-v", "error", "-show_streams", "-show_format",
                        "-of", "json", str(path)], text=True))
                    streams = info.get("streams", [])
                    videos = [s for s in streams if s.get("codec_type") == "video"]
                    duration = float(info["format"]["duration"])
                    if not videos or not math.isfinite(duration) or duration <= start:
                        raise ValueError("No usable video stream or evaluation interval")
                    if end is not None and end > duration + 0.05:
                        raise ValueError("Evaluation interval exceeds video duration")
                    if out["layout"] == "with_prefix":
                        source_duration = source_video_duration(dataset_root, case)
                        if abs(start - source_duration) > 0.05:
                            raise ValueError("Prefix boundary differs from source duration")
                    if case["scenario"] == "AVIR":
                        if not any(s.get("codec_type") == "audio" for s in streams):
                            raise ValueError("AVIR requires an audio stream")
                        if case.get("task") != "audio_video_continuation":
                            if abs(duration - source_video_duration(dataset_root, case)) > 0.1:
                                raise ValueError("AVIR annotation output duration differs from source")
                        if end is not None and abs(end - duration) > 0.05:
                            raise ValueError("AVIR must evaluate the full output ending")
                    if case["scenario"] == "MSR" and videos[0]["width"] <= videos[0]["height"]:
                        raise ValueError("MSR requires a wide side-by-side video")
            counts[status] = counts.get(status, 0) + 1
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            errors.append({"id": cid, "error": str(exc)})
    expected = {cid for cid, r in cases.items() if r["scenario"] in scope}
    missing = sorted(expected - seen)
    return {"expected_cases": len(expected), "submitted_ids": len(seen), "status_counts": counts,
            "missing_ids": missing, "errors": errors, "valid": not missing and not errors,
            "media_probe": probe,
            "note": "Structural validation only; this does not produce benchmark scores."}


def source_video_duration(root: Path, case: dict) -> float:
    asset = case["inputs"]["video"]
    if asset.get("duration_s") is not None:
        return asset["duration_s"]
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
        str(resolve_asset(root, asset["path"]))], text=True))
    return float(info["format"]["duration"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    report = validate_submission(args.dataset_root, args.submission, args.probe)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

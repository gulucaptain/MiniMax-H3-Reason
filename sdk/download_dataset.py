#!/usr/bin/env python3
"""Download benchmark data at a resolved Hub commit, without any model API calls."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluator.runner import load_dataset, dump

DEFAULT_REPO = 'gulucaptain/MiniMax-H3-Reason'
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / 'datasets/MiniMax-H3-Reason'


def download(repo_id, revision, output, api=None, snapshot=None):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Output already exists; select a new directory for a different dataset revision.')
    if api is None or snapshot is None:
        from huggingface_hub import HfApi, snapshot_download
        api = api or HfApi()
        snapshot = snapshot or snapshot_download
    # Resolve branch/tag once, then pin every downloaded file to that commit.
    info = api.dataset_info(repo_id=repo_id, revision=revision)
    commit = info.sha
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
        raise ValueError('Hub did not return a full dataset commit SHA.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dataset-download-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'data-package'
        snapshot(repo_id=repo_id, repo_type='dataset', revision=commit,
                 local_dir=str(stage), allow_patterns=['data/**', 'media/**'])
        meta, cases, refs, audio = load_dataset(stage)
        dump(stage / 'download_metadata.json', {
            'repo_id': repo_id, 'revision': commit, 'requested_revision': revision,
            'downloaded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'manifest_sha256': meta['manifest_sha256'],
            'references_sha256': meta['references_sha256'],
            'audio_evidence_sha256': meta['audio_evidence_sha256']})
        os.replace(stage, output)
    return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-id', default=DEFAULT_REPO)
    parser.add_argument('--revision', default='main', help='Branch, tag or commit; resolved to a fixed commit before download.')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    try:
        commit = download(args.repo_id, args.revision, args.output_dir)
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        parser.exit(2, 'Dataset download failed: ' + str(exc) + '\n')
    print('Dataset revision: ' + commit)
    print('Dataset root: ' + str(args.output_dir.resolve()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

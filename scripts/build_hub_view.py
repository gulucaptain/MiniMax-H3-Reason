"""Build a lightweight Hub media view; canonical case/media files remain unchanged."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

DEFAULT_REPO = 'gulucaptain/MiniMax-H3-Reason'


def write_media_browser(root, repo_id=DEFAULT_REPO):
    root = Path(root)
    if len(repo_id.split('/')) != 2 or any(not part or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for c in part) for part in repo_id.split('/')):
        raise ValueError('repo_id must be namespace/dataset-name.')
    cases = [json.loads(line) for line in (root / 'data/cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    rows = []
    for case in cases:
        row = {key: case[key] for key in ('id', 'scenario', 'subcategory', 'task', 'prompt')}
        for kind in ('image', 'audio', 'video'):
            asset = case['inputs'][kind]
            row[kind] = None if asset is None else {'bytes': None, 'path': f'https://huggingface.co/datasets/{repo_id}/resolve/main/{quote(asset["path"], safe="/")}'}
        rows.append(row)
    folder = root / 'data/hub'; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'media_preview.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    (folder / 'metadata.json').write_text(json.dumps({'repo_id': repo_id, 'revision': 'main', 'case_count': len(rows),
        'source_manifest': 'data/cases.jsonl', 'purpose': 'Hub browsing only; the SDK and evaluator use the canonical manifest.'}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--repo-id', default=DEFAULT_REPO)
    args = parser.parse_args()
    write_media_browser(args.dataset_root, args.repo_id)

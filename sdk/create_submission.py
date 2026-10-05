#!/usr/bin/env python3
"""Import videos named CASE-ID.mp4/.mov/.mkv/.webm into a canonical submission."""
import argparse
import json
from pathlib import Path
import shutil
import sys

# Allow execution as sdk/create_submission.py from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk.interface import read_jsonl
from evaluator.runner import load_dataset, dump
from evaluator import media


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, default=Path(__file__).resolve().parents[1] / 'datasets/MiniMax-H3-Reason')
    parser.add_argument('--videos-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model-id', required=True)
    parser.add_argument('--model-version', default='unspecified')
    parser.add_argument('--scenarios', nargs='+', choices=['ADR', 'VDR', 'AVIR', 'MSR'], default=['ADR', 'VDR', 'AVIR', 'MSR'])
    parser.add_argument('--vdr-layout', choices=['continuation_only', 'with_prefix'], default='continuation_only')
    parser.add_argument('--avir-layout', choices=['continuation_only', 'with_prefix'], default='continuation_only',
                        help='Layout for AVIR prediction cases; annotation cases keep annotated_full_video.')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    args = parser.parse_args()
    try:
        dataset, cases, _, _ = load_dataset(args.dataset_root.resolve())
        selected = [c for c in cases.values() if c['scenario'] in args.scenarios]
        if not args.videos_dir.is_dir():
            raise ValueError('Video directory does not exist.')
        if args.output_dir.exists():
            raise ValueError('Output directory already exists; choose a new directory.')
        index = {}
        for path in args.videos_dir.iterdir():
            if path.is_file() and path.suffix.lower() in {'.mp4', '.mov', '.mkv', '.webm'}:
                if path.stem not in {c['id'] for c in selected}:
                    raise ValueError('Unknown or out-of-scope video filename: ' + path.name)
                if path.stem in index:
                    raise ValueError('Multiple videos for case ID: ' + path.stem)
                index[path.stem] = path
        if not index:
            raise ValueError('No videos named with a selected case ID.')
        if args.vdr_layout == 'with_prefix' or args.avir_layout == 'with_prefix':
            media.configure(args.ffmpeg, args.ffprobe)
        # Compute boundaries before creating any submission files.
        boundaries = {}
        for case in selected:
            prefix_layout = (case['scenario'] == 'VDR' and args.vdr_layout == 'with_prefix' or
                             case.get('task') == 'audio_video_continuation' and args.avir_layout == 'with_prefix')
            if case['id'] in index and prefix_layout:
                from sdk.interface import resolve_asset
                boundaries[case['id']] = media.probe(resolve_asset(args.dataset_root, case['inputs']['video']['path']))['duration_s']
        videos = args.output_dir / 'videos'
        videos.mkdir(parents=True)
        rows = []
        for case in selected:
            cid = case['id']
            if cid not in index:
                rows.append({'id': cid, 'status': 'skipped', 'reason': 'No video supplied.', 'output': None})
                continue
            path = index[cid]
            shutil.copyfile(path, videos / path.name)
            layout = (args.avir_layout if case.get('task') == 'audio_video_continuation' else
                      args.vdr_layout if case['scenario'] == 'VDR' else case['output_spec']['allowed_layouts'][0])
            rows.append({'id': cid, 'status': 'ok', 'output': {'kind': 'video', 'path': 'videos/' + path.name,
                         'layout': layout, 'evaluation_start_s': boundaries.get(cid, 0), 'evaluation_end_s': None}})
        dump(args.output_dir / 'submission.json', {
            'schema_version': '0.1.0', 'dataset_manifest_sha256': dataset['manifest_sha256'],
            'model_id': args.model_id, 'model_version': args.model_version,
            'adapter_version': 'case-id-video-import-1.0', 'scope': args.scenarios,
            'preprocessing': [], 'generation_config': {}, 'seed': None,
        })
        (args.output_dir / 'outputs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        print(f'Imported {len(index)} videos; {len(rows) - len(index)} cases recorded as skipped.')
        print('Record actual preprocessing, generation parameters and seed in submission.json before reporting results.')
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())

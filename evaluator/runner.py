"""Evaluate canonical submissions and report every selected case."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import subprocess

from sdk.interface import read_jsonl, resolve_asset, validate_submission
from . import eval_adr, eval_vdr, eval_avir, eval_avir_continuation, eval_msr, media
from .client import api_call, validate_config, resolve_config, JudgeConfigurationError
from .preflight import check_judge

VERSION = 'video-evaluator-1.3.0'
PROTOCOLS = {'ADR': eval_adr, 'VDR': eval_vdr, 'AVIR': eval_avir, 'MSR': eval_msr}


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        temporary = stream.name
    os.replace(temporary, path)


def run_preflight(judge, report_dir):
    path = report_dir / 'judge_preflight.json'
    dump(path, {'status': 'pending'})
    try:
        result = check_judge(judge)
    except (ValueError, RuntimeError, OSError) as exc:
        dump(path, {'status': 'error', 'reason': str(exc)})
        raise
    dump(path, {'status': 'passed', **result})


def dataset_provenance(root):
    path = root / 'download_metadata.json'
    if not path.is_file():
        return {'source': 'local', 'repo_id': None, 'revision': None}
    info = json.loads(path.read_text())
    meta = json.loads((root / 'data/dataset.json').read_text())
    if any(info.get(key) != meta[key] for key in ('manifest_sha256', 'references_sha256', 'audio_evidence_sha256')):
        raise ValueError('Downloaded revision metadata differs from dataset manifest.')
    return {'source': 'huggingface', 'repo_id': info.get('repo_id'), 'revision': info.get('revision')}


def toolkit_git_commit():
    try:
        return subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def unique_rows(path):
    result = {}
    for row in read_jsonl(path):
        cid = row.get('id')
        if not isinstance(cid, str) or cid in result:
            raise ValueError('Missing or duplicate ID in ' + path.name)
        result[cid] = row
    return result


def load_dataset(root):
    meta = json.loads((root / 'data/dataset.json').read_text())
    for name, key in [('data/cases.jsonl', 'manifest_sha256'),
                      ('data/evaluation/references.jsonl', 'references_sha256'),
                      ('data/evaluation/audio_evidence.jsonl', 'audio_evidence_sha256')]:
        if file_hash(root / name) != meta[key]:
            raise ValueError('Dataset hash mismatch: ' + name)
    cases = unique_rows(root / 'data/cases.jsonl')
    refs = unique_rows(root / 'data/evaluation/references.jsonl')
    audio = unique_rows(root / 'data/evaluation/audio_evidence.jsonl')
    if len(cases) != meta['case_count'] or set(refs) != set(cases):
        raise ValueError('Case/reference inventory differs from dataset metadata.')
    for cid, case in cases.items():
        if case['scenario'] not in PROTOCOLS or case['schema_version'] != '0.1.0':
            raise ValueError('Unsupported dataset case protocol: ' + cid)
        ref = refs[cid]
        if ref.get('status') != 'available' or not ref.get('plausible_outcomes'):
            raise ValueError('Missing reference: ' + cid)
    return meta, cases, refs, audio


def summarize(rows):
    counts = Counter(r['label'] for r in rows)
    n = len(rows)
    passed, failed = counts['pass'], counts['fail']
    generation_failures = sum(counts[x] for x in ('generation_error', 'unsupported', 'skipped'))
    blocked = counts['error'] + counts['dry_run'] + counts['pending']
    return {
        'n': n, 'pass': passed, 'fail': failed, 'unknown': counts['unknown'],
        'generation_error': counts['generation_error'], 'unsupported': counts['unsupported'],
        'skipped': counts['skipped'], 'evaluator_error': counts['error'],
        'dry_run': counts['dry_run'], 'pending': counts['pending'],
        'task_success_rate': passed / n if n and not blocked else None,
        'decision_coverage': (passed + failed) / n if n else None,
        'decidable_success_rate': passed / (passed + failed) if passed + failed else None,
        'success_rate_bounds': [passed / n, (n - failed - generation_failures) / n] if n and not blocked else None,
        'complete': bool(n) and not blocked,
    }


def write_reports(folder, rows, cases, config, dataset, submission_meta):
    protocol_versions = {s: p.VERSION for s, p in PROTOCOLS.items()}
    report = {
        'evaluator_version': VERSION, 'dataset_manifest_sha256': dataset['manifest_sha256'],
        'references_sha256': dataset['references_sha256'],
        'dataset_scenario_counts': dataset['scenario_counts'],
        'selected_case_ids': [c['id'] for c in cases],
        'full_declared_scope': len(cases) == sum(dataset['scenario_counts'][s] for s in config['scope']),
        'submission_metadata': submission_meta, 'config': config, 'protocol_versions': protocol_versions,
        'assessment_weights': {s: p.ASSESSMENT_WEIGHTS for s, p in PROTOCOLS.items()},
        'overall': summarize(rows),
        'scenarios': {s: summarize([r for r in rows if r['scenario'] == s]) for s in PROTOCOLS},
        'avir_subtasks': {task: summarize([r for r in rows if r.get('task') == task])
                         for task in ('audio_video_annotation', 'audio_video_continuation')},
        'avir_subtask_protocols': {
            'audio_video_annotation': {'version': eval_avir.VERSION, 'weights': eval_avir.ASSESSMENT_WEIGHTS},
            'audio_video_continuation': {'version': eval_avir_continuation.VERSION, 'weights': eval_avir_continuation.ASSESSMENT_WEIGHTS}},
        'metric_definition': 'Confirmed task successes divided by every selected case. Unknown and generation failures remain in the denominator. Evaluator errors, pending cases and dry runs make the rate null. See decision coverage and bounds.',
    }
    dump(folder / 'summary.json', report)
    dump(folder / 'results.json', rows)
    dump(folder / 'review_queue.json', [r for r in rows if r['label'] in {'unknown', 'error'}])
    with (folder / 'results.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['id', 'scenario', 'execution_status', 'label', 'reference_label', 'weighted_score', 'reason'])
        for row in rows:
            writer.writerow([row.get(k) for k in ['id', 'scenario', 'execution_status', 'label', 'reference_label', 'weighted_score', 'reason']])
    return report


def evaluate_case(case, output, refs, audio, root, submission_root, folder, args, config):
    cid, scenario = case['id'], case['scenario']
    continuation = scenario == 'AVIR' and case.get('task') == 'audio_video_continuation'
    protocol = eval_avir_continuation if continuation else PROTOCOLS[scenario]
    record = {'id': cid, 'scenario': scenario, 'execution_status': output['status'],
              'task': case.get('task'), 'subcategory': case.get('subcategory'), 'label': 'error', 'reference_label': None,
              'prompt': case['prompt'], 'plausible_outcomes': refs[cid]['plausible_outcomes']}
    result_path = folder / 'evaluation.json'
    if output['status'] != 'ok':
        record.update(label='generation_error' if output['status'] == 'error' else output['status'],
                      reason=output['reason'])
        dump(result_path, record)
        return record
    try:
        assets, hashes = {}, {}
        for kind, asset in case['inputs'].items():
            if asset is None:
                continue
            path = resolve_asset(root, asset['path'])
            actual = file_hash(path)
            if actual != asset['sha256']:
                raise ValueError('Source media hash mismatch: ' + kind)
            assets[kind] = path
            hashes[kind] = actual
        out = output['output']
        video = resolve_asset(submission_root, out['path'])
        hashes['output'] = file_hash(video)
        fingerprint = digest([case, output, hashes, refs[cid], audio.get(cid), config])
        record.update(fingerprint=fingerprint, media_sha256=hashes)
        if args.resume and result_path.is_file():
            previous = json.loads(result_path.read_text())
            if previous.get('fingerprint') == fingerprint and previous.get('label') in {'pass', 'fail', 'unknown', 'dry_run'}:
                return previous
        info = media.probe(video)
        duration = info['duration_s']
        if not info['video_streams'] or duration <= 0:
            raise ValueError('No decodable output video stream or duration.')
        start, end = out['evaluation_start_s'], out.get('evaluation_end_s')
        # Full outputs must be assessed completely; participants cannot hide a failing ending.
        if end is not None and abs(end - duration) > 0.05:
            record.update(label='fail', reason='The evaluation interval must include the complete output ending.')
            dump(result_path, record)
            return record
        end = duration
        if (scenario == 'VDR' or continuation) and out['layout'] == 'with_prefix':
            prefix_duration = media.probe(assets['video'])['duration_s']
            if abs(start - prefix_duration) > 0.05:
                record.update(label='fail', reason='Continuation boundary does not equal source duration.')
                dump(result_path, record)
                return record
        if not 0 <= start < end:
            record.update(label='fail', reason='No generated video in the evaluation interval.')
            dump(result_path, record)
            return record
        if scenario == 'AVIR' and not continuation and abs(duration - media.probe(assets['video'])['duration_s']) > 0.1:
            record.update(label='fail', reason='AVIR output must preserve the complete source timeline.')
            dump(result_path, record)
            return record
        if scenario == 'MSR' and info['video_streams'][0]['width'] <= info['video_streams'][0]['height']:
            record.update(label='fail', reason='MSR output must use a wide side-by-side layout.')
            dump(result_path, record)
            return record
        source = [{'type': 'text', 'text': json.dumps({'evidence_id': 'prompt', 'task_prompt': case['prompt']})}]
        evidence = []
        if scenario in {'ADR', 'MSR'}:
            prefix = 'image' if scenario == 'ADR' else 'source'
            blocks, evidence = media.extract(assets['image'], prefix, 1, args.max_side, folder / 'evidence', image=True)
        else:
            prefix = 'input' if scenario == 'VDR' else 'source'
            blocks, evidence = media.extract(assets['video'], prefix, args.input_frames, args.max_side, folder / 'evidence')
        source += blocks
        source_ids = {'prompt'} | {r['id'] for r in evidence}
        if scenario in {'ADR', 'AVIR'}:
            caption = audio.get(cid)
            if caption is None or caption['audio_sha256'] != hashes['audio']:
                raise ValueError('Missing or mismatched hash-bound audio description.')
            description = {'evidence_id': 'audio_description', **caption}
            source.append({'type': 'text', 'text': json.dumps(description)})
            source_ids.add('audio_description')
            record['audio_evidence'] = description
        ob, output_evidence = media.extract(video, 'output', args.output_frames, args.max_side,
                                            folder / 'evidence', start=start, end=end)
        record.update(frame_evidence=evidence + output_evidence, output_duration_s=duration,
                      evaluation_start_s=start, evaluation_end_s=end)
        if scenario == 'AVIR':
            audit = (protocol.waveform_audio_audit(assets['audio'], video) if info['audio_streams'] else
                     {'score': 0, 'reason': 'Output has no audio stream.', 'evidence_id': 'audio_audit'})
            record['audio_audit'] = audit
        if args.dry_run:
            record.update(label='dry_run', reason='Source hashes, media decoding and frame extraction checked; no judge API calls or task scores.')
        else:
            prediction, raw = api_call([{'role': 'system', 'content': protocol.BASE + protocol.PREDICTION_PROMPT},
                                        {'role': 'user', 'content': source}], config['judge'])
            record['prediction_raw_response'] = raw
            dump(result_path, record)
            protocol.validate_prediction(prediction, source_ids)
            record['model_prediction'] = prediction
            if not prediction['input_sufficient']:
                record.update(label='unknown', reference_label='unknown', reason='Source evidence does not support a reliable independent prediction.')
            else:
                context = {'human_curated_plausible_outcomes': refs[cid]['plausible_outcomes'],
                           'blind_model_prediction': prediction, 'assessment_weights': protocol.ASSESSMENT_WEIGHTS,
                           'output_duration_s': duration, 'output_segment_start_s': start,
                           'instruction': 'Assess the submitted generated output using the scenario protocol.'}
                judgment, raw = api_call([{'role': 'system', 'content': protocol.BASE + protocol.JUDGE_PROMPT},
                    {'role': 'user', 'content': source + [{'type': 'text', 'text': json.dumps(context)}] + ob}], config['judge'])
                record['judgment_raw_response'] = raw
                dump(result_path, record)
                allowed = source_ids | {r['id'] for r in output_evidence}
                params = [judgment, prediction, refs[cid]['plausible_outcomes'], allowed]
                if scenario == 'AVIR':
                    params.append(record['audio_audit'])
                values = protocol.validate_judgment(*params)
                label, reference_label, score = values[:3]
                if scenario == 'AVIR':
                    judgment['assessments'] = values[3]
                record.update(label=label, reference_label=reference_label, weighted_score=score,
                              judgment=judgment, reason=judgment['reasoning_explanation'])
    except JudgeConfigurationError as exc:
        record.update(label='error', reason=str(exc))
        dump(result_path, record)
        raise
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        record.update(label='error', reason=str(exc))
    dump(result_path, record)
    return record


def main(default_scenarios=None):
    parser = argparse.ArgumentParser(description='Evaluate generated videos for ADR, VDR, AVIR and MSR.')
    parser.add_argument('--dataset-root', type=Path, default=Path(__file__).resolve().parents[1] / 'datasets/MiniMax-H3-Reason')
    parser.add_argument('--submission', type=Path, help='Canonical outputs.jsonl (required for scoring)')
    parser.add_argument('--report-dir', type=Path, default=Path('evaluation_results'))
    parser.add_argument('--judge-config', type=Path)
    parser.add_argument('--judge-provider', choices=['compatible', 'deepseek', 'kimi', 'openai'])
    parser.add_argument('--check-judge', action='store_true', help='Check image and JSON support without a submission.')
    parser.add_argument('--judge-base-url', default=os.environ.get('JUDGE_BASE_URL'))
    parser.add_argument('--judge-model', default=os.environ.get('JUDGE_MODEL'))
    parser.add_argument('--api-key-env', default=None)
    parser.add_argument('--prompt-key', action='store_true', help='Read the judge key privately for this process only.')
    parser.add_argument('--scenarios', nargs='+', choices=list(PROTOCOLS), default=default_scenarios)
    parser.add_argument('--case-ids', nargs='+', help='Explicit subset for testing; reported as a subset, never a full benchmark.')
    parser.add_argument('--input-frames', type=int, default=8)
    parser.add_argument('--output-frames', type=int, default=20)
    parser.add_argument('--max-side', type=int, default=1280)
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        if not 2 <= args.input_frames <= 120 or not 2 <= args.output_frames <= 120 or not 128 <= args.max_side <= 4096:
            raise ValueError('Frame counts must be 2-120 and max-side must be 128-4096.')
        supplied = json.loads(args.judge_config.read_text()) if args.judge_config else {}
        judge = resolve_config(supplied, {'provider': args.judge_provider, 'base_url': args.judge_base_url,
                               'model': args.judge_model, 'api_key_env': args.api_key_env})
        if args.check_judge and args.dry_run:
            raise ValueError('--check-judge makes an API call and cannot be combined with --dry-run.')
        if not args.check_judge and args.submission is None:
            raise ValueError('--submission is required for scoring.')
        if not args.dry_run:
            if args.prompt_key:
                import getpass
                os.environ[judge['api_key_env']] = getpass.getpass('Judge API key (hidden): ')
            validate_config(judge)
        if args.check_judge:
            run_preflight(judge, args.report_dir)
            print('Judge image and JSON compatibility check passed.')
            return 0
        if args.submission is None:
            raise ValueError('--submission is required for scoring.')
        root, submission = args.dataset_root.resolve(), args.submission.resolve()
        dataset, all_cases, refs, audio = load_dataset(root)
        validation = validate_submission(root, submission)
        if not validation['valid']:
            dump(args.report_dir / 'validation.json', validation)
            raise ValueError('Submission validation failed; see validation.json in report-dir.')
        submission_meta = json.loads((submission.parent / 'submission.json').read_text())
        for field in ('model_id', 'model_version', 'adapter_version'):
            if submission_meta[field].startswith('REPLACE_'):
                raise ValueError('Fill the actual submission metadata: ' + field)
        scope = args.scenarios or submission_meta['scope']
        if not set(scope) <= set(submission_meta['scope']):
            raise ValueError('Requested scenarios are outside the submission scope.')
        cases = [c for c in all_cases.values() if c['scenario'] in scope]
        if args.case_ids:
            if len(set(args.case_ids)) != len(args.case_ids) or not set(args.case_ids) <= {c['id'] for c in cases}:
                raise ValueError('Unknown, duplicated or out-of-scope case IDs.')
            cases = [c for c in cases if c['id'] in args.case_ids]
        outputs = unique_rows(submission)
        if not any(outputs[c['id']]['status'] == 'ok' for c in cases):
            raise ValueError('No generated videos to evaluate in the selected scope.')
        backend = media.configure(args.ffmpeg, args.ffprobe)
        code_root = Path(__file__).resolve().parents[1]
        code_hash = digest({str(p.relative_to(code_root)): file_hash(p) for folder in ('evaluator', 'sdk') for p in (code_root / folder).glob('*.py')})
        config = {'version': VERSION, 'code_sha256': code_hash, 'scope': scope,
                  'input_frames': args.input_frames, 'output_frames': args.output_frames,
                  'max_side': args.max_side, 'dry_run': args.dry_run, 'judge': judge,
                  'media_backend': backend, 'references_sha256': dataset['references_sha256'],
                  'audio_evidence_sha256': dataset['audio_evidence_sha256'],
                  'submission_metadata_sha256': digest(submission_meta),
                  'dataset_provenance': dataset_provenance(root),
                  'toolkit_git_commit': toolkit_git_commit()}
        rows = [{'id': c['id'], 'scenario': c['scenario'], 'task': c.get('task'), 'label': 'pending'} for c in cases]
        write_reports(args.report_dir, rows, cases, config, dataset, submission_meta)
        if not args.dry_run:
            run_preflight(judge, args.report_dir)
        for i, case in enumerate(cases):
            print(f'[{i + 1}/{len(cases)}] {case["id"]}: evaluating', flush=True)
            try:
                rows[i] = evaluate_case(case, outputs[case['id']], refs, audio, root, submission.parent,
                                        args.report_dir / case['id'], args, config)
            except JudgeConfigurationError as exc:
                rows[i].update(label='error', reason=str(exc))
                write_reports(args.report_dir, rows, cases, config, dataset, submission_meta)
                raise
            report = write_reports(args.report_dir, rows, cases, config, dataset, submission_meta)
            print('  ' + rows[i]['label'] + ': ' + rows[i].get('reason', ''), flush=True)
        print('\nScenario     N     Pass     Task success     Coverage')
        for scenario, metrics in report['scenarios'].items():
            rate = metrics['task_success_rate']
            rate_text = f'{rate:.2%}' if rate is not None else 'N/A'
            coverage = metrics['decision_coverage']
            coverage_text = f'{coverage:.2%}' if coverage is not None else 'N/A'
            print(f'{scenario:<10} {metrics["n"]:<5} {metrics["pass"]:<8} {rate_text:<16} {coverage_text}')
        print('Report: ' + str((args.report_dir / 'summary.json').resolve()))
        return 1 if any(r['label'] == 'error' for r in rows) else 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(2, 'Evaluation setup error: ' + str(exc) + '\n')

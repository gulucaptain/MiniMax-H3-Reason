"""Offline integration tests: actual FFmpeg decoding, deterministic mock judge responses."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# The same test file works in both the publication source and the release package.
ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'sdk').is_dir():
    ROOT = ROOT.parents[1] / 'auto-eval-ds-release-draft'
sys.path.insert(0, str(ROOT))
from evaluator import runner, media, client


def mocked_judge(messages, config):
    system = messages[0]['content']
    if 'Audio-driven' in system:
        scenario, source = 'ADR', 'image:0'
    elif 'Video-based' in system:
        scenario, source = 'VDR', 'input:0'
    elif 'Audio-Video' in system:
        scenario, source = 'AVIR', 'source:0'
    else:
        scenario, source = 'MSR', 'source:0'
    if 'STAGE 1' in system:
        fields = ['task_question', 'prediction_basis', 'observed_image_state', 'audio_interpretation',
                  'observed_state', 'observed_source_state', 'left_view_observation',
                  'right_view_observation', 'cross_view_correspondence', 'observed_visual_event',
                  'consistency_prediction', 'continuation_prediction']
        obj = {f: 'Observed fixture evidence.' for f in fields}
        obj.update(input_sufficient=True, model_predicted_outcomes=['Fixture outcome.'],
                   prediction_evidence_ids=[source, 'prompt'], contradiction_targets=[], limitations=[])
    else:
        p = (runner.eval_avir_continuation if 'AVIR_CONTINUATION' in system else runner.PROTOCOLS[scenario])
        names = p.MODEL_ASSESSMENTS if scenario == 'AVIR' else p.ASSESSMENT_WEIGHTS
        assessments = []
        for name in names:
            item = {'id': name, 'score': 2, 'reason': 'Mock judge fixture only.',
                    'evidence_ids': [source, 'output:0'],
                    'matched_outcome_indices': [0] if name in {'HUMAN_REFERENCE', 'MODEL_PREDICTION'} else []}
            if name == 'HUMAN_REFERENCE':
                item.update(applicable_outcome_indices=[0], unmet_outcome_indices=[])
            assessments.append(item)
        obj = {key: 'Mock judge fixture only.' for key in ['observed_result', 'cross_view_analysis',
               'observed_source_event', 'observed_output_result', 'audio_visual_analysis', 'reasoning_explanation']}
        obj['assessments'] = assessments
    return obj, {'fixture': True}


class EvaluatorIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.dataset = cls.base / 'dataset'
        cls.submission = cls.base / 'submission'
        cls.dataset.mkdir(); cls.submission.mkdir()
        (cls.dataset / 'data/evaluation').mkdir(parents=True)
        cls.backend = media.configure()
        ff = media.FFMPEG
        image = cls.dataset / 'source.png'
        video = cls.dataset / 'source.mp4'
        audio = cls.dataset / 'source.wav'
        for args in [
            ['-f', 'lavfi', '-i', 'color=c=blue:s=640x320:d=1', '-frames:v', '1', str(image)],
            ['-f', 'lavfi', '-i', 'color=c=blue:s=640x320:d=1', '-pix_fmt', 'yuv420p', str(video)],
            ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=8000:duration=1', str(audio)],
        ]:
            media.run_cmd([ff, '-v', 'error', '-y'] + args)
        cases, refs, descriptions, outputs = [], [], [], []
        for scenario in runner.PROTOCOLS:
            cid = scenario + '-001'
            inputs = {'image': None, 'audio': None, 'video': None}
            for kind, asset in [('image', image), ('audio', audio), ('video', video)]:
                if (kind == 'image' and scenario in {'ADR', 'MSR'} or
                    kind == 'audio' and scenario in {'ADR', 'AVIR'} or
                    kind == 'video' and scenario in {'VDR', 'AVIR'}):
                    inputs[kind] = {'path': asset.name, 'sha256': runner.file_hash(asset)}
            layouts = {'ADR': 'full_video', 'VDR': 'continuation_only', 'AVIR': 'annotated_full_video', 'MSR': 'side_by_side'}
            task = {'ADR': 'audio_conditioned_generation', 'VDR': 'video_continuation',
                    'AVIR': 'audio_video_annotation', 'MSR': 'synchronized_dual_view_generation'}[scenario]
            cases.append({'id': cid, 'scenario': scenario, 'task': task, 'schema_version': '0.1.0', 'subcategory': 'fixture',
                          'prompt': 'Fixture task.', 'inputs': inputs,
                          'output_spec': {'allowed_layouts': [layouts[scenario]]}})
            refs.append({'id': cid, 'status': 'available', 'plausible_outcomes': ['Fixture outcome.']})
            if scenario in {'ADR', 'AVIR'}:
                descriptions.append({'id': cid, 'audio_sha256': runner.file_hash(audio),
                                     'description': 'A sustained tone.', 'description_source': 'human_fixture'})
            out = cls.submission / (cid + '.mp4')
            if scenario == 'AVIR':
                media.run_cmd([ff, '-v', 'error', '-y', '-i', str(video), '-i', str(audio),
                               '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', str(out)])
            else:
                out.write_bytes(video.read_bytes())
            outputs.append({'id': cid, 'status': 'ok', 'output': {'kind': 'video', 'path': out.name,
                'layout': layouts[scenario], 'evaluation_start_s': 0, 'evaluation_end_s': None}})
        for filename, rows in [('data/cases.jsonl', cases), ('data/evaluation/references.jsonl', refs),
                               ('data/evaluation/audio_evidence.jsonl', descriptions)]:
            (cls.dataset / filename).write_text(''.join(json.dumps(r) + '\n' for r in rows))
        cls.metadata = {'schema_version': '0.1.0', 'case_count': 4,
            'scenario_counts': {s: 1 for s in runner.PROTOCOLS},
            'manifest_sha256': runner.file_hash(cls.dataset / 'data/cases.jsonl'),
            'references_sha256': runner.file_hash(cls.dataset / 'data/evaluation/references.jsonl'),
            'audio_evidence_sha256': runner.file_hash(cls.dataset / 'data/evaluation/audio_evidence.jsonl')}
        runner.dump(cls.dataset / 'data/dataset.json', cls.metadata)
        runner.dump(cls.submission / 'submission.json', {'schema_version': '0.1.0',
            'dataset_manifest_sha256': cls.metadata['manifest_sha256'], 'scope': list(runner.PROTOCOLS),
            'model_id': 'fixture', 'model_version': '1', 'adapter_version': '1'})
        cls.outputs = outputs
        cls.output_file = cls.submission / 'outputs.jsonl'
        cls.write_outputs(outputs)

    @classmethod
    def write_outputs(cls, rows):
        cls.output_file.write_text(''.join(json.dumps(r) + '\n' for r in rows))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.write_outputs(self.outputs)

    def invoke(self, report, extra=(), api=mocked_judge):
        argv = ['evaluate.py', '--dataset-root', str(self.dataset), '--submission', str(self.output_file),
                '--report-dir', str(report), '--judge-base-url', 'https://judge.example/v1',
                '--judge-model', 'fixture-vision', '--api-key-env', 'TEST_JUDGE_KEY',
                '--input-frames', '2', '--output-frames', '2', '--max-side', '320', *extra]
        with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'TEST_JUDGE_KEY': 'fixture-only'}), \
             patch.object(runner, 'check_judge', return_value={'fixture': True}), \
             patch.object(runner, 'api_call', side_effect=api) as called, patch('sys.stdout', new=io.StringIO()):
            status = runner.main()
        return status, called.call_count

    def test_all_scenarios_and_resume(self):
        report = self.base / 'all'
        code, calls = self.invoke(report)
        self.assertEqual((code, calls), (0, 8))
        result = json.loads((report / 'summary.json').read_text())
        self.assertTrue(result['full_declared_scope'])
        self.assertEqual(result['overall']['n'], 4)
        for scenario in runner.PROTOCOLS:
            self.assertEqual(result['scenarios'][scenario]['task_success_rate'], 1)
        code, calls = self.invoke(report, ['--resume'])
        self.assertEqual((code, calls), (0, 0))

    def test_dry_run_does_not_call_judge_or_score(self):
        report = self.base / 'dry'
        code, calls = self.invoke(report, ['--dry-run'])
        self.assertEqual((code, calls), (0, 0))
        data = json.loads((report / 'summary.json').read_text())
        self.assertEqual(data['overall']['dry_run'], 4)
        self.assertIsNone(data['overall']['task_success_rate'])

    def test_generation_failures_remain_in_denominator(self):
        rows = copy.deepcopy(self.outputs)
        rows[0] = {'id': 'ADR-001', 'status': 'error', 'output': None, 'reason': 'Generation failed.'}
        self.write_outputs(rows)
        report = self.base / 'generation-failure'
        code, calls = self.invoke(report)
        self.assertEqual((code, calls), (0, 6))
        data = json.loads((report / 'summary.json').read_text())
        self.assertEqual(data['scenarios']['ADR']['n'], 1)
        self.assertEqual(data['scenarios']['ADR']['task_success_rate'], 0)
        self.assertEqual(data['overall']['task_success_rate'], 0.75)

    def test_judge_errors_null_rate_and_retry(self):
        report = self.base / 'retry'
        code, _ = self.invoke(report, api=lambda *a: (_ for _ in ()).throw(RuntimeError('Mock network failure.')))
        self.assertEqual(code, 1)
        self.assertIsNone(json.loads((report / 'summary.json').read_text())['overall']['task_success_rate'])
        code, calls = self.invoke(report, ['--resume'])
        self.assertEqual((code, calls), (0, 8))

    def test_fatal_judge_configuration_stops_and_preserves_pending(self):
        report = self.base / 'fatal-configuration'
        def fatal(*args):
            raise client.JudgeConfigurationError('Judge HTTP 401: mock authentication failure.')
        with self.assertRaises(SystemExit) as stopped:
            self.invoke(report, api=fatal)
        self.assertEqual(stopped.exception.code, 2)
        data = json.loads((report / 'summary.json').read_text())
        self.assertEqual(data['overall']['evaluator_error'], 1)
        self.assertEqual(data['overall']['pending'], 3)
        self.assertEqual(data['overall']['fail'], 0)
        self.assertIsNone(data['overall']['task_success_rate'])
        records = json.loads((report / 'results.json').read_text())
        self.assertEqual(sum(row['label'] == 'error' for row in records), 1)

    def test_subset_is_explicit(self):
        report = self.base / 'subset'
        code, calls = self.invoke(report, ['--case-ids', 'VDR-001'])
        self.assertEqual((code, calls), (0, 2))
        data = json.loads((report / 'summary.json').read_text())
        self.assertFalse(data['full_declared_scope'])
        self.assertEqual(data['selected_case_ids'], ['VDR-001'])
        self.assertIsNone(data['scenarios']['ADR']['task_success_rate'])

    def test_full_end_required(self):
        rows = copy.deepcopy(self.outputs)
        rows[1]['output']['evaluation_end_s'] = 0.5
        self.write_outputs(rows)
        report = self.base / 'crop'
        code, calls = self.invoke(report, ['--case-ids', 'VDR-001'])
        self.assertEqual((code, calls), (0, 0))
        self.assertEqual(json.loads((report / 'results.json').read_text())[0]['label'], 'fail')

    def test_source_hash_mismatch_prevents_api(self):
        meta = json.loads((self.dataset / 'data/dataset.json').read_text())
        bad = dict(meta, references_sha256='0' * 64)
        runner.dump(self.dataset / 'data/dataset.json', bad)
        try:
            with self.assertRaises(SystemExit) as exc:
                self.invoke(self.base / 'bad-hash')
            self.assertEqual(exc.exception.code, 2)
        finally:
            runner.dump(self.dataset / 'data/dataset.json', meta)

    def test_with_prefix_and_resume_boundary_change(self):
        ff = media.FFMPEG
        original = self.submission / 'VDR-001.mp4'
        prefixed = self.submission / 'VDR-001-prefix.mp4'
        media.run_cmd([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=640x320:d=2', str(prefixed)])
        rows = copy.deepcopy(self.outputs)
        rows[1]['output'].update(path=prefixed.name, layout='with_prefix', evaluation_start_s=1)
        manifest_path = self.dataset / 'data/cases.jsonl'
        metadata_path = self.dataset / 'data/dataset.json'
        submission_meta_path = self.submission / 'submission.json'
        backups = {p: p.read_bytes() for p in [manifest_path, metadata_path, submission_meta_path]}
        cases = runner.read_jsonl(manifest_path)
        cases[1]['output_spec']['allowed_layouts'].append('with_prefix')
        manifest_path.write_text(''.join(json.dumps(r) + '\n' for r in cases))
        meta = json.loads(metadata_path.read_text());meta['manifest_sha256'] = runner.file_hash(manifest_path)
        runner.dump(metadata_path, meta)
        sm = json.loads(submission_meta_path.read_text());sm['dataset_manifest_sha256'] = meta['manifest_sha256']
        runner.dump(submission_meta_path, sm)
        try:
            self.write_outputs(rows)
            report = self.base / 'prefix'
            code, calls = self.invoke(report, ['--case-ids', 'VDR-001'])
            self.assertEqual((code, calls), (0, 2))
            output_frames = [r for r in json.loads((report / 'results.json').read_text())[0]['frame_evidence'] if r['id'].startswith('output:')]
            self.assertGreaterEqual(output_frames[0]['time_s'], 1)
            rows[1]['output']['evaluation_start_s'] = 0.7
            self.write_outputs(rows)
            code, calls = self.invoke(report, ['--case-ids', 'VDR-001', '--resume'])
            self.assertEqual((code, calls), (0, 0))
            self.assertEqual(json.loads((report / 'results.json').read_text())[0]['label'], 'fail')
        finally:
            for path, data in backups.items():
                path.write_bytes(data)

    def test_avir_prediction_routes_both_layouts(self):
        ff = media.FFMPEG
        prediction_video = self.submission / 'AVIR-019.mp4'
        future = self.base / 'future.mp4'
        media.run_cmd([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=640x320:d=2', str(future)])
        media.run_cmd([ff, '-v', 'error', '-y', '-i', str(future), '-i', str(self.dataset / 'source.wav'),
                       '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', str(prediction_video)])
        paths = [self.dataset / 'data/cases.jsonl', self.dataset / 'data/evaluation/references.jsonl',
                 self.dataset / 'data/evaluation/audio_evidence.jsonl', self.dataset / 'data/dataset.json',
                 self.submission / 'submission.json']
        backups = {p: p.read_bytes() for p in paths}
        try:
            for p in paths[:3]:
                rows = runner.read_jsonl(p)
                for row in rows:
                    if row['id'] == 'AVIR-001':
                        row['id'] = 'AVIR-019'
                        if p.name == 'cases.jsonl':
                            row['task'] = 'audio_video_continuation'
                            row['output_spec']['allowed_layouts'] = ['continuation_only', 'with_prefix']
                p.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            meta = json.loads(paths[3].read_text())
            for p, key in zip(paths[:3], ['manifest_sha256', 'references_sha256', 'audio_evidence_sha256']):
                meta[key] = runner.file_hash(p)
            runner.dump(paths[3], meta)
            sm = json.loads(paths[4].read_text()); sm['dataset_manifest_sha256'] = meta['manifest_sha256']
            runner.dump(paths[4], sm)
            for layout, start in [('continuation_only', 0), ('with_prefix', 1)]:
                rows = copy.deepcopy(self.outputs)
                rows[2]['id'] = 'AVIR-019'
                rows[2]['output'].update(path=prediction_video.name, layout=layout, evaluation_start_s=start)
                self.write_outputs(rows)
                report = self.base / ('avir-prediction-' + layout)
                code, calls = self.invoke(report, ['--case-ids', 'AVIR-019'])
                self.assertEqual((code, calls), (0, 2))
                result = json.loads((report / 'results.json').read_text())[0]
                self.assertEqual(result['label'], 'pass')
                self.assertEqual(result['task'], 'audio_video_continuation')
                self.assertEqual(result['evaluation_start_s'], start)
                names = {a['id'] for a in result['judgment']['assessments']}
                self.assertIn('AUDIOVISUAL_REASONING', names)
                self.assertNotIn('ANNOTATION_CORRECTNESS', names)
                summary = json.loads((report / 'summary.json').read_text())
                self.assertEqual(summary['scenarios']['AVIR']['n'], 1)
                self.assertEqual(summary['avir_subtasks']['audio_video_continuation']['pass'], 1)
        finally:
            for path, data in backups.items():
                path.write_bytes(data)


class MetricsAndClient(unittest.TestCase):
    def test_unknown_is_not_removed(self):
        m = runner.summarize([{'label': 'pass'}] * 10 + [{'label': 'unknown'}] * 10)
        self.assertEqual(m['task_success_rate'], 0.5)
        self.assertEqual(m['decidable_success_rate'], 1)
        self.assertEqual(m['decision_coverage'], 0.5)

    def test_invalid_evidence_rejected(self):
        messages = [{'content': runner.eval_vdr.BASE + runner.eval_vdr.JUDGE_PROMPT}]
        obj, _ = mocked_judge(messages, {})
        obj['assessments'][0]['evidence_ids'] = ['output:999']
        with self.assertRaises(ValueError):
            runner.eval_vdr.validate_judgment(obj, {'model_predicted_outcomes': ['one']}, ['one'], {'output:0', 'input:0'})

    def test_client_uses_configurable_key_and_url(self):
        config = {'base_url': 'https://judge.example/v1', 'model': 'vision-fixture',
                  'api_key_env': 'TEST_JUDGE_KEY', 'timeout': 1, 'retries': 0,
                  'max_tokens': 1024, 'request_options': {'thinking': {'type': 'disabled'}}}
        raw = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]}
        with patch.dict(os.environ, {'TEST_JUDGE_KEY': 'fixture-only'}), \
             patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(raw).encode())) as opened:
            value, _ = client.api_call([{'role': 'user', 'content': 'fixture'}], config)
        self.assertTrue(value['ok'])
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, 'https://judge.example/v1/chat/completions')
        self.assertEqual(json.loads(request.data)['thinking']['type'], 'disabled')

    def test_published_avir_modes_match_prompts(self):
        dataset = Path(os.environ.get('MINIMAX_H3_DATASET_ROOT', ROOT / 'datasets/MiniMax-H3-Reason'))
        if not (dataset / 'data/cases.jsonl').is_file():
            self.skipTest('Download the dataset to verify published task counts.')
        cases = runner.read_jsonl(dataset / 'data/cases.jsonl')
        avir = [c for c in cases if c['scenario'] == 'AVIR']
        self.assertEqual(sum(c['task'] == 'audio_video_annotation' for c in avir), 48)
        self.assertEqual(sum(c['task'] == 'audio_video_continuation' for c in avir), 23)
        for case in avir:
            self.assertEqual(case['task'] == 'audio_video_annotation', 'red circle' in case['prompt'].lower())



if __name__ == '__main__':
    unittest.main()

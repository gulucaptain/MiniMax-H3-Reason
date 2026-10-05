"""Offline provider contracts: no credentials or real network requests required."""
import base64
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import urllib.error
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'sdk').is_dir():
    ROOT = ROOT.parents[1] / 'auto-eval-ds-release-draft'
sys.path.insert(0, str(ROOT))
from evaluator import client, preflight, runner


def response(content, finish='stop', **message):
    return {'model': 'fixture-model', 'choices': [{'finish_reason': finish, 'message': {'content': content, **message}}]}


class ProviderContracts(unittest.TestCase):
    def test_provider_payloads_and_endpoints(self):
        for provider in client.PROVIDERS:
            with self.subTest(provider=provider):
                cfg = client.resolve_config({'provider': provider})
                if provider == 'compatible':
                    cfg.update(base_url='https://fixture.example/v1', model='fixture-vision')
                images = [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': preflight.color_image((255, 0, 0))}}]}]
                with patch.dict(os.environ, {cfg['api_key_env']: 'offline-fixture'}), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response('{"ok":true}')).encode())) as opened:
                    client.validate_config(cfg)
                    result, _ = client.api_call(images, cfg)
                req = opened.call_args.args[0]
                body = json.loads(req.data)
                self.assertTrue(result['ok'])
                self.assertEqual(req.full_url, cfg['base_url'].rstrip('/') + '/chat/completions')
                self.assertEqual(body['messages'], images)
                self.assertIn(cfg['token_field'], body)
                self.assertNotIn('max_tokens' if cfg['token_field'] == 'max_completion_tokens' else 'max_completion_tokens', body)
                self.assertEqual(body.get('thinking'), {'type': 'disabled'} if provider in {'kimi', 'deepseek'} else None)

    def test_normalizes_final_content_only(self):
        for content in ['{"ok":true}', '```json\n{"ok":true}\n```', [{'type': 'text', 'text': '{"ok":true}'}]]:
            self.assertEqual(client.parse_response(response(content, reasoning_content='not JSON')), {'ok': True})
        for raw in [response('{"ok":true}', finish='length'), response('{}', refusal='refused'), response(None, reasoning_content='{}'), response('[]'), response('{"x":NaN}'), response('{"x":1,"x":2}'), response('Explanation: {}')]:
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                client.parse_response(raw)

    def test_retry_and_fatal_http(self):
        cfg = client.resolve_config({'provider': 'openai', 'retries': 1})
        with patch.dict(os.environ, {cfg['api_key_env']: 'offline-fixture'}):
            for status in (400, 401, 403, 404, 422):
                error = urllib.error.HTTPError('https://fixture.example', status, 'secret-provider-body', {}, None)
                with patch('urllib.request.urlopen', side_effect=error) as opened, self.assertRaises(client.JudgeConfigurationError) as caught:
                    client.api_call([], cfg)
                self.assertEqual(opened.call_count, 1)
                self.assertNotIn('secret-provider-body', str(caught.exception))
            transient = urllib.error.HTTPError('https://fixture.example', 429, 'rate', {}, None)
            with patch('urllib.request.urlopen', side_effect=[transient, io.BytesIO(json.dumps(response('{}')).encode())]) as opened, patch.object(client.time, 'sleep'):
                self.assertEqual(client.api_call([], cfg)[0], {})
                self.assertEqual(opened.call_count, 2)

    def test_config_rejects_managed_overrides(self):
        for key in ('api_key', 'max_tokens', 'max_completion_tokens', 'response_format', 'messages', 'stream'):
            cfg = client.resolve_config({'provider': 'openai', 'request_options': {key: 'bad'}})
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-fixture'}), self.assertRaises(ValueError):
                client.validate_config(cfg)
        with self.assertRaises(ValueError):
            client.resolve_config({'api_key': 'must-not-be-stored'})

    def test_preflight_inspects_actual_image_bytes(self):
        cfg = client.resolve_config({'provider': 'openai'})
        def transport(req, **kwargs):
            content = json.loads(req.data)['messages'][0]['content']
            colors = []
            for block in content[1:]:
                png = base64.b64decode(block['image_url']['url'].split(',')[1])
                offset = 8
                while offset < len(png):
                    length = struct.unpack('>I', png[offset:offset+4])[0]
                    if png[offset+4:offset+8] == b'IDAT':
                        rgb = tuple(zlib.decompress(png[offset+8:offset+8+length])[1:4])
                        colors.append(next(name for name, value in preflight.COLORS.items() if value == rgb))
                    offset += length + 12
            return io.BytesIO(json.dumps(response(json.dumps({'colors': colors, 'image_count': len(colors)}))).encode())
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-fixture'}), patch('urllib.request.urlopen', side_effect=transport) as opened:
            result = preflight.check_judge(cfg)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(result['response_model'], 'fixture-model')
        self.assertTrue(all(result['checks'].values()))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-fixture'}), patch.object(preflight, 'api_call', return_value=({'colors': [], 'image_count': 0}, {})), self.assertRaises(client.JudgeConfigurationError):
            preflight.check_judge(cfg)

    def test_failed_preflight_overwrites_previous_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'judge_preflight.json').write_text('{"status":"passed"}')
            with patch.object(runner, 'check_judge', side_effect=client.JudgeConfigurationError('Mock unsupported images.')), self.assertRaises(client.JudgeConfigurationError):
                runner.run_preflight({}, path)
            self.assertEqual(json.loads((path / 'judge_preflight.json').read_text())['status'], 'error')

    def test_cli_preflight_requires_no_submission_or_decoder(self):
        with tempfile.TemporaryDirectory() as folder:
            argv = ['evaluate.py', '--judge-provider', 'openai', '--check-judge', '--report-dir', folder]
            with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-fixture'}), patch.object(runner, 'check_judge', return_value={'fixture': True}) as checked, patch.object(runner.media, 'configure') as decoder, patch('sys.stdout', new=io.StringIO()):
                self.assertEqual(runner.main(), 0)
            checked.assert_called_once()
            decoder.assert_not_called()
            self.assertTrue((Path(folder) / 'judge_preflight.json').is_file())


if __name__ == '__main__':
    unittest.main()

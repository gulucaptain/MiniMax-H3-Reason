"""Offline publication contracts; no Hub credentials or requests."""
import json
from pathlib import Path
import re
import sys
import os
import unittest
from urllib.parse import unquote,urlsplit

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'sdk').is_dir():
    ROOT = ROOT.parents[1] / 'auto-eval-ds-release-draft'

ROOT = Path(os.environ.get('MINIMAX_H3_DATASET_ROOT', ROOT / 'datasets/MiniMax-H3-Reason'))


@unittest.skipUnless((ROOT / 'data/hub/media_preview.jsonl').is_file(), 'Download dataset for publication checks.')
class HubPackageContracts(unittest.TestCase):
    def test_browsing_view_matches_all_inputs_without_answers(self):
        cases = {r['id']: r for r in (json.loads(line) for line in (ROOT/'data/cases.jsonl').read_text().splitlines())}
        rows = [json.loads(line) for line in (ROOT/'data/hub/media_preview.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),517)
        self.assertEqual(set(cases),{r['id'] for r in rows})
        self.assertEqual(sum(r['image'] is not None for r in rows),346)
        self.assertEqual(sum(r['audio'] is not None for r in rows),217)
        self.assertEqual(sum(r['video'] is not None for r in rows),171)
        for row in rows:
            self.assertEqual(set(row),{'id','scenario','subcategory','task','prompt','image','audio','video'})
            self.assertEqual(row['prompt'],cases[row['id']]['prompt'])
            for kind in ('image','audio','video'):
                original = cases[row['id']]['inputs'][kind]
                if original is None:
                    self.assertIsNone(row[kind])
                else:
                    self.assertIsNone(row[kind]['bytes'])
                    path=unquote(urlsplit(row[kind]['path']).path.split('/resolve/main/',1)[1])
                    self.assertEqual(path,original['path'])
                    self.assertTrue((ROOT/path).is_file())

    def test_homepage_local_links_and_preview_assets(self):
        for path in (ROOT/'README.md',ROOT/'docs/README.en.md'):
            text=path.read_text()
            self.assertTrue(text.startswith('---\n'))
            for target in re.findall(r'\]\(([^)]+)\)',text):
                if not target.startswith(('http:','https:','#')):
                    self.assertTrue((path.parent/target).exists(),target)
        for name in ('overview.jpg','ADR-001.jpg','VDR-001.gif','AVIR-001.gif','MSR-001.jpg'):
            self.assertGreater((ROOT/'assets/previews'/name).stat().st_size,1000)


if __name__ == '__main__':
    unittest.main()

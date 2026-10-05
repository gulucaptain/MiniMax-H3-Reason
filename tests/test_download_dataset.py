"""Versioned data downloads tested with a local snapshot mock, without Hub/API calls."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sdk.download_dataset import download
from evaluator.runner import dataset_provenance


class DownloadContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.source=self.base/'source'
        (self.source/'data/evaluation').mkdir(parents=True)
        rows={'data/cases.jsonl':[{'id':'VDR-001','scenario':'VDR','schema_version':'0.1.0'}],
              'data/evaluation/references.jsonl':[{'id':'VDR-001','status':'available','plausible_outcomes':['Fixture.']}],
              'data/evaluation/audio_evidence.jsonl':[]}
        for name,value in rows.items():(self.source/name).write_text(''.join(json.dumps(x)+'\n' for x in value))
        self.meta={'case_count':1}
        for name,key in zip(rows,['manifest_sha256','references_sha256','audio_evidence_sha256']):self.meta[key]=hashlib.sha256((self.source/name).read_bytes()).hexdigest()
        (self.source/'data/dataset.json').write_text(json.dumps(self.meta))
        self.api=Mock();self.api.dataset_info.return_value=SimpleNamespace(sha='a'*40)
        self.snapshot=Mock(side_effect=lambda **kwargs:shutil.copytree(self.source,kwargs['local_dir']))

    def test_resolves_once_pins_snapshot_and_records_hashes(self):
        out=self.base/'download'
        self.assertEqual(download('owner/data','main',out,self.api,self.snapshot),'a'*40)
        self.snapshot.assert_called_once()
        args=self.snapshot.call_args.kwargs
        self.assertEqual(args['revision'],'a'*40)
        self.assertEqual(args['allow_patterns'],['data/**','media/**'])
        self.assertEqual(dataset_provenance(out),{'source':'huggingface','repo_id':'owner/data','revision':'a'*40})
        meta=json.loads((out/'download_metadata.json').read_text());self.assertEqual(meta['references_sha256'],self.meta['references_sha256'])
        meta['audio_evidence_sha256']='changed';(out/'download_metadata.json').write_text(json.dumps(meta))
        with self.assertRaises(ValueError):dataset_provenance(out)

    def test_bad_download_is_not_published(self):
        (self.source/'data/cases.jsonl').write_text('bad manifest')
        out=self.base/'download'
        with self.assertRaises(ValueError):download('owner/data','main',out,self.api,self.snapshot)
        self.assertFalse(out.exists())
        self.assertFalse(list(self.base.glob('.dataset-download-*')))

    def test_existing_output_is_never_overwritten(self):
        out=self.base/'download';out.mkdir();(out/'user-file').write_text('keep')
        with self.assertRaises(ValueError):download('owner/data','main',out,self.api,self.snapshot)
        self.api.dataset_info.assert_not_called();self.assertEqual((out/'user-file').read_text(),'keep')

    def test_local_data_without_download_provenance(self):
        self.assertEqual(dataset_provenance(self.source)['source'],'local')


if __name__=='__main__':unittest.main()

"""Synthetic embeddings and dependency-free boundary tests, NOT model inference."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import contract as C
import run as runner


def preprocessing():
    return {'feature_extractor_type':'ClapFeatureExtractor','sampling_rate':48000,
        'max_length_s':10,'chunk_length_s':10,'nb_max_samples':480000,
        'padding':'repeatpad','truncation':'fusion','padding_side':'right','padding_value':0.0}


def fixture():
    return {'schema_version':1,'model':{'id':'synthetic-fixture','revision':'not-a-model',
        'files':{k:'a'*64 for k in C.MODEL_FILES}},'packages':{k:'fixture' for k in C.PACKAGES},
        'labels':[{'id':'event_a','text':'An illustrative event A.'},{'id':'event_b','text':'An illustrative event B.'}],
        'assets':[{'id':'neutral','path':'neutral.wav','sha256':'b'*64,'expected_label':'event_a',
            'windows':[{'start_seconds':0,'duration_seconds':1}]}]}


class ShadowTests(unittest.TestCase):
    def test_rank_and_mismatch_are_not_probability_or_rejection(self):
        x=C.rank(fixture()['labels'],[[1,0],[0,1]],[0,2],'event_a')
        self.assertEqual(x['ranking'],['event_b','event_a']);self.assertEqual(x['hint'],'expected_label_not_top')
        self.assertFalse(x['hint_is_rejection']);self.assertEqual(x['cosine_similarity']['event_b'],1)

    def test_ties_keep_label_order_without_false_mismatch(self):
        x=C.rank(fixture()['labels'],[[1,0],[1,0]],[1,0],'event_b')
        self.assertEqual(x['ranking'],['event_a','event_b']);self.assertEqual(x['hint'],'none')
        self.assertEqual(x['top_minus_second'],0)

    def test_scale_and_negative_cosine(self):
        x=C.rank(fixture()['labels'],[[1e308,0],[-1e308,0]],[-1e308,0])
        self.assertEqual(x['cosine_similarity'],{'event_a':-1.,'event_b':1.})

    def test_bad_embeddings_rejected(self):
        for a in ([0,0],[float('nan'),1],[float('inf'),1],[1],[True,1],[10**10000,1]):
            with self.subTest(kind=type(a[0]).__name__):
                with self.assertRaises(ValueError):C.rank(fixture()['labels'],[[1,0],[0,1]],a)

    def test_contract_errors(self):
        changes=[lambda x:x.update(schema_version=True),lambda x:x['labels'].append(x['labels'][0]),
                 lambda x:x['model']['files'].pop('model.safetensors'),lambda x:x['packages'].pop('torch'),
                 lambda x:x['assets'][0].update(expected_label='absent'),lambda x:x['assets'].append(x['assets'][0]),
                 lambda x:x['assets'][0]['windows'][0].update(duration_seconds=11),
                 lambda x:x['assets'][0]['windows'][0].update(start_seconds=-1),
                 lambda x:x['assets'][0]['windows'][0].update(start_seconds=10**10000)]
        for change in changes:
            lock=fixture();change(lock)
            with self.assertRaises(ValueError):C.validate(lock)

    def test_report_identity_and_fixture_scope(self):
        lock=fixture();row={'asset_id':'neutral','window_index':0,**C.rank(lock['labels'],[[1,0],[0,1]],[1,0],'event_a')}
        r=C.report(lock,[row],evidence_kind='synthetic_embedding_fixture',versions=lock['packages'])
        self.assertEqual(r['mode'],'shadow');self.assertFalse(r['gating']);self.assertFalse(r['quality_approval'])
        self.assertFalse(r['perception_verified']);self.assertEqual(r['listening_status'],'not_assessed')
        self.assertNotIn('path',r['assets'][0]);self.assertEqual(r['evidence_kind'],'synthetic_embedding_fixture')
        for mutate in (lambda x:x['labels'][0].update(text='changed'),lambda x:x['assets'][0]['windows'][0].update(duration_seconds=2),lambda x:x['model'].update(revision='other')):
            changed=copy.deepcopy(lock);mutate(changed)
            other=C.report(changed,[row],evidence_kind='synthetic_embedding_fixture',versions=changed['packages'])
            self.assertNotEqual(r['lock_sha256'],other['lock_sha256'])

    def test_partial_and_wrong_order_rejected(self):
        with self.assertRaises(ValueError):C.report(fixture(),[],evidence_kind='synthetic_embedding_fixture',versions={})
        with self.assertRaises(ValueError):C.report(fixture(),[{'asset_id':'wrong','window_index':0}],evidence_kind='synthetic_embedding_fixture',versions={})

    def test_lock_duplicate_json_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'lock.json'
            for text in ('{"x":1,"x":2}','{"x":NaN}'):
                p.write_text(text)
                with self.assertRaises(ValueError):C.load(p)

    def test_model_missing_changed_and_unrecorded_files_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);lock=fixture()
            for name in C.MODEL_FILES:
                (root/name).write_bytes(b'synthetic-not-a-model');lock['model']['files'][name]=C.sha(root/name)
            (root/'preprocessor_config.json').write_text(json.dumps(preprocessing()))
            lock['model']['files']['preprocessor_config.json']=C.sha(root/'preprocessor_config.json')
            self.assertEqual(runner.resolve_model(root,lock),root)
            (root/'untrusted.py').write_text('')
            with self.assertRaises(ValueError):runner.resolve_model(root,lock)
            (root/'untrusted.py').unlink();(root/'config.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):runner.resolve_model(root,lock)

    def test_preprocessing_contract_cannot_silently_change(self):
        self.assertEqual(C.validate_preprocessor(preprocessing()),preprocessing())
        for key,value in [('padding','pad'),('truncation','rand_trunc'),('max_length_s',20),
                          ('chunk_length_s',20),('nb_max_samples',960000),('sampling_rate',44100),
                          ('padding_side','left'),('padding_value',True)]:
            config=preprocessing();config[key]=value
            with self.assertRaises(ValueError):C.validate_preprocessor(config)
        with self.assertRaises(ValueError):C.validate_preprocessor({})

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'output';p.write_text('preserve')
            self.assertEqual(runner.main(['missing.json','--model-dir',d,'--output',str(p)]),2)
            self.assertEqual(p.read_text(),'preserve')

    def test_decode_failure_and_cap_not_partial_success(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'decoded'
            with patch.object(runner.subprocess,'run',return_value=type('R',(),{'returncode':1})()):
                with self.assertRaises(ValueError):runner.decode(Path('fixture'),'ffmpeg',out)
            out.write_bytes(b'bad')
            with patch.object(runner.subprocess,'run',return_value=type('R',(),{'returncode':0})()):
                with self.assertRaises(ValueError):runner.decode(Path('fixture'),'ffmpeg',out)

    def test_import_and_help_do_not_require_model_packages(self):
        # -S removes site-packages; this checks CLI loading, not model execution.
        r=subprocess.run([sys.executable,'-S',str(Path(runner.__file__)),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertNotIn('torch',sys.modules);self.assertNotIn('transformers',sys.modules)

    def test_offline_loading_flags_are_explicit(self):
        text=Path(runner.__file__).read_text()
        self.assertEqual(text.count('local_files_only=True'),3)
        self.assertIn('use_safetensors=True,trust_remote_code=False',text)
        self.assertIn("HF_HUB_DISABLE_TELEMETRY='1'",text)
        self.assertNotIn('pip install',text);self.assertNotIn('snapshot_download',text)


if __name__=='__main__':unittest.main(verbosity=2)

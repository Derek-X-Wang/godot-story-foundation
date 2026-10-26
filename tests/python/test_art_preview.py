"""Static preview checks; no aesthetic acceptance or real browser claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.art.characters.pipeline import build as build_character
from tools.art.manifest import ArtError, digest
from tools.art.preview.build import build

ROOT = Path(__file__).resolve().parents[2]

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        bundle = self.root / 'sprite'
        build_character(ROOT / 'examples/art/characters/broad.json', bundle)
        self.atlas = json.loads((bundle/'atlas.json').read_text())
        self.spec = {'title': 'Synthetic <review>', 'assets': [
            {'asset_id': self.atlas['asset_id'], 'label':'Animation', 'kind':'animation',
             'image':{'path':'sprite/atlas.png','sha256':digest(bundle/'atlas.png')},
             'atlas':{'path':'sprite/atlas.json','sha256':digest(bundle/'atlas.json')}},
            {'asset_id':'neutral_scene', 'label':'Still example, not scene art', 'kind':'scene',
             'image':{'path':'sprite/atlas.png','sha256':digest(bundle/'atlas.png')}}]}
        self.index = self.root/'index.json'
    def run_build(self, name='out'):
        self.index.write_text(json.dumps(self.spec))
        return build(self.index,self.root/name)
    def test_deterministic_relocatable_minimal_output(self):
        a=self.run_build('a');b=self.run_build('b')
        self.assertEqual(a,b)
        self.assertEqual(len(a['assets']),2)
        self.assertNotIn('build-record.json',a['files'])
        self.assertNotIn('source_sha256',(self.root/'a/catalog.js').read_text())
        for name in a['files']:
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())
        with self.assertRaises(ArtError):self.run_build('a')
    def test_responsive_template_is_delivered(self):
        self.run_build()
        html=(self.root/'out/index.html').read_text()
        # Static template regression only; actual layout needs browser measurement.
        for rule in ('class="resource-controls"', 'grid-template-columns:minmax(0,1fr)',
                     'width:100%;min-width:0', '#identity,#position,#error,#direct',
                     'overflow-wrap:anywhere', '#direct{display:block;margin:1rem 0 .9rem}',
                     'textarea{margin:.3rem 0}'):
            self.assertIn(rule,html)

    def test_version_changes_with_playback(self):
        a=self.run_build('a')['assets'][0]['version']
        p=self.root/'sprite/atlas.json';d=json.loads(p.read_text());d['frames'][0]['duration_ms']+=1;d['tags'][0]['durations_ms'][0]+=1;p.write_text(json.dumps(d))
        self.spec['assets'][0]['atlas']['sha256']=digest(p)
        self.assertNotEqual(a,self.run_build('b')['assets'][0]['version'])
    def test_versions_can_coexist_but_duplicates_cannot(self):
        self.spec['assets'].append(copy.deepcopy(self.spec['assets'][0]))
        with self.assertRaises(ArtError):self.run_build()
        self.assertFalse((self.root/'out').exists())
    def test_source_hash_and_path_fail_closed(self):
        for field,value in [('sha256','0'*64),('path','../outside.png'),('path','/tmp/outside.png')]:
            original=copy.deepcopy(self.spec)
            self.spec['assets'][0]['image'][field]=value
            with self.assertRaises(ArtError):self.run_build()
            self.assertFalse((self.root/'out').exists());self.spec=original
    def test_malformed_atlas(self):
        p=self.root/'sprite/atlas.json';original=p.read_text()
        for mutation in ['rect','timing','identity','loop']:
            d=json.loads(original)
            if mutation=='rect':d['frames'][0]['rect'][2]=999999
            if mutation=='timing':d['tags'][0]['durations_ms'][0]+=1
            if mutation=='identity':d['asset_id']='wrong'
            if mutation=='loop':d['tags'][0]['loop']='false'
            p.write_text(json.dumps(d));self.spec['assets'][0]['atlas']['sha256']=digest(p)
            with self.assertRaises(ArtError):self.run_build()
    def test_still_and_animation_are_explicit(self):
        self.spec['assets'][0]['kind']='scene'
        with self.assertRaises(ArtError):self.run_build()
    def test_private_extra_fields_do_not_publish(self):
        p=self.root/'sprite/atlas.json';d=json.loads(p.read_text());d['private']='SECRET';d['frames'][0]['private']='SECRET';d['tags'][0]['private']='SECRET';p.write_text(json.dumps(d));self.spec['assets'][0]['atlas']['sha256']=digest(p)
        self.run_build();self.assertNotIn('SECRET',(self.root/'out/catalog.js').read_text())

if __name__=='__main__':unittest.main()

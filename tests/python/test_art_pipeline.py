from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.art.characters.contract import validate_manifest
from tools.art.characters.pipeline import build
from tools.art.manifest import ArtError, canonical, digest, read_json
from tools.art.png import decode, encode


class CharacterArtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for p in (ROOT / 'examples/art/characters').glob('*'):
            if p.suffix in ('.json', '.png'): shutil.copy2(p, self.root / p.name)
        self.path = self.root / 'narrow.json'
        self.m = read_json(self.path)

    def write(self, value=None):
        self.path.write_bytes(canonical(self.m if value is None else value))

    def test_two_fixture_reuse_and_determinism(self):
        for fixture in ('narrow', 'broad'):
            with self.subTest(fixture=fixture):
                path = self.root / f'{fixture}.json'
                before = path.with_suffix('.png').read_bytes()
                first, second = self.root / f'{fixture}-a', self.root / f'{fixture}-b'
                build(path, first, godot=True)
                build(path, second, godot=True)
                self.assertEqual({p.name:p.read_bytes() for p in first.iterdir()}, {p.name:p.read_bytes() for p in second.iterdir()})
                self.assertEqual(before, path.with_suffix('.png').read_bytes())
                self.assertFalse(any(p.suffix == '.aseprite' for p in first.iterdir()))
                self.assertEqual(read_json(first/'build-record.json')['rights_clearance'], 'not_determined_by_tool')

    def test_fixture_regeneration_is_identical(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('fixtures', ROOT/'examples/art/characters/create_fixtures.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        destination=self.root/'regenerated'; module.create(destination)
        for p in destination.iterdir(): self.assertEqual(p.read_bytes(), (self.root/p.name).read_bytes())

    def test_unknown_rights_fail_closed_with_explicit_exploration(self):
        self.m['provenance']['license']='unknown'; self.write()
        with self.assertRaisesRegex(ArtError,'unknown provenance'): build(self.path)
        report=build(self.path, allow_unknown_provenance=True)
        self.assertIn('UNKNOWN_PROVENANCE', report['warnings'][0])
        self.assertEqual(report['rights_clearance'], 'not_determined_by_tool')

    def test_origin_never_selects_a_provider(self):
        for origin in ('original','ai_assisted','licensed'):
            self.m['provenance']['origin']=origin; self.write()
            self.assertEqual(build(self.path)['adapter']['adapter'], 'png')

    def test_contract_rejections(self):
        def change(path, value):
            m=copy.deepcopy(self.m); current=m
            for key in path[:-1]: current=current[key]
            current[path[-1]]=value
            return m
        cases=[(['schema_version'],2),(['schema_version'],True),(['kind'],'portrait'),(['asset_id'],'../oops'),
               (['cell'],[0,12]),(['cell'],[True,12]),(['pivot'],[9,11]),(['columns'],0),(['hard_alpha'],False),
               (['palette'],['#ffffff80']),(['palette'],['#ff000000']),(['palette'],['#00000000','#00000000']),
               (['tags',0,'start'],1),(['tags',0,'count'],3),(['tags',0,'durations_ms'],[0,240]),
               (['tags',0,'name'],'bad name'),(['tags',0,'loop'],'true'),(['source','sha256'],'bad'),
               (['source','adapter'],'generator'),(['provenance','rights'],'approved')]
        for path,value in cases:
            with self.subTest(path=path,value=value):
                with self.assertRaises(ArtError): validate_manifest(change(path,value))
        for scope in (self.m,self.m['source'],self.m['tags'][0],self.m['provenance']):
            scope['unexpected']=1
            with self.assertRaises(ArtError): validate_manifest(self.m)
            del scope['unexpected']

    def test_partition_overlap_gap_duplicate(self):
        self.m['tags']=[dict(name='a',start=0,count=1,durations_ms=[100],loop=True),dict(name='b',start=1,count=1,durations_ms=[100],loop=False)]
        validate_manifest(self.m)
        for field,value in [('start',0),('start',2),('name','a')]:
            bad=copy.deepcopy(self.m); bad['tags'][1][field]=value
            with self.assertRaises(ArtError): validate_manifest(bad)

    def test_checksum_path_and_symlink(self):
        for path in ('../narrow.png','/tmp/narrow.png','a//b.png','a\\b.png'):
            self.m['source']['path']=path; self.write()
            with self.assertRaises(ArtError): build(self.path)
        self.m['source']['path']='narrow.png'; self.m['source']['sha256']='0'*64; self.write()
        with self.assertRaisesRegex(ArtError,'SHA-256 mismatch'): build(self.path)
        outside=self.root.parent/(self.root.name+'-outside.png')
        outside.write_bytes((self.root/'narrow.png').read_bytes()); self.addCleanup(outside.unlink)
        (self.root/'link.png').symlink_to(outside)
        self.m['source']['path']='link.png'; self.m['source']['sha256']=digest(outside); self.write()
        with self.assertRaisesRegex(ArtError,'escaped directory'): build(self.path)

    def mutate_pixels(self, mutate):
        p=self.root/'narrow.png'; w,h,pixels=decode(p.read_bytes()); pixels=bytearray(pixels)
        mutate(pixels); p.write_bytes(encode(w,h,pixels)); self.m['source']['sha256']=digest(p); self.write()

    def test_hard_alpha(self):
        self.mutate_pixels(lambda p:p.__setitem__(slice(0,4),b'\x29\x31\x48\x80'))
        with self.assertRaisesRegex(ArtError,'hard alpha'): build(self.path)

    def test_palette(self):
        self.mutate_pixels(lambda p:p.__setitem__(slice(0,4),b'\xff\x00\x00\xff'))
        with self.assertRaisesRegex(ArtError,'absent from palette'): build(self.path)

    def test_empty_frames(self):
        self.mutate_pixels(lambda p:p.__setitem__(slice(None),b'\0'*len(p)))
        with self.assertRaisesRegex(ArtError,'empty frame'): build(self.path)

    def test_grid(self):
        self.m['cell'][0]=9; self.write()
        with self.assertRaisesRegex(ArtError,'grid'): build(self.path)

    def test_nonempty_padding_cell(self):
        self.path=self.root/'broad.json'; self.m=read_json(self.path)
        self.m['columns']=2; self.m['tags'][0]['count']=3
        p=self.root/'broad.png'; w,h,pixels=decode(p.read_bytes())
        # A four-cell sheet with all cells opaque and only three declared frames.
        p.write_bytes(encode(24,24,bytes.fromhex('243d47ff')*(24*24)))
        self.m['source']['sha256']=digest(p);self.write()
        with self.assertRaisesRegex(ArtError,'padding cell'):build(self.path)

    def test_output_never_overwrites_and_failure_leaves_no_bundle(self):
        out=self.root/'build';out.mkdir();(out/'keep').write_text('unchanged')
        with self.assertRaisesRegex(ArtError,'already exists'):build(self.path,out)
        self.assertEqual((out/'keep').read_text(),'unchanged')
        self.m['source']['sha256']='0'*64;self.write()
        with self.assertRaises(ArtError):build(self.path,self.root/'failure')
        self.assertFalse((self.root/'failure').exists())
        self.assertFalse(list(self.root.glob('.art-stage-*')))

    def test_native_layer_bound_matches_schema(self):
        self.m['source']['adapter']='aseprite'
        self.m['source']['layers']=[f'layer_{i}' for i in range(4096)]
        validate_manifest(self.m)
        self.m['source']['layers'].append('layer_4096')
        with self.assertRaisesRegex(ArtError,'4096'):validate_manifest(self.m)

    def test_native_adapter_is_explicit(self):
        self.m['source']['adapter']='aseprite';self.write()
        with self.assertRaisesRegex(ArtError,'requires --aseprite'):build(self.path)

    def test_duplicate_json_fields(self):
        self.path.write_text('{"asset_id": "a", "asset_id": "b"}')
        with self.assertRaisesRegex(ArtError,'duplicate JSON'):read_json(self.path)

    def test_cli_returns_nonzero_on_rejection(self):
        self.m['pivot']=[100,100];self.write()
        result=subprocess.run([sys.executable,'-m','tools.art','validate',str(self.path)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertIn('pivot',result.stderr)


class PngTests(unittest.TestCase):
    def chunk(self,kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    def png(self,color,raw,extra=b'',depth=8,interlace=0):
        return b'\x89PNG\r\n\x1a\n'+self.chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,depth,color,0,0,interlace))+extra+self.chunk(b'IDAT',zlib.compress(raw))+self.chunk(b'IEND',b'')
    def test_roundtrip_and_alpha_canonicalization(self):
        self.assertEqual(decode(encode(2,1,b'\x12\x34\x56\x00\xff\x00\x00\xff')),(2,1,b'\0\0\0\0\xff\x00\x00\xff'))
    def test_rgb_and_indexed(self):
        expected=b'\x10\x20\x30\xff\x40\x50\x60\xff'
        self.assertEqual(decode(self.png(2,b'\0\x10\x20\x30\x40\x50\x60'))[2],expected)
        palette=self.chunk(b'PLTE',b'\x10\x20\x30\x40\x50\x60')
        self.assertEqual(decode(self.png(3,b'\0\0\1',palette))[2],expected)
        self.assertEqual(decode(self.png(3,b'\0\0\1',palette+self.chunk(b'tRNS',b'\0')))[2],b'\0'*4+expected[4:])
    def test_all_filters(self):
        # Two identical pixels: second pixel differs according to each predictor.
        for method,raw in [(0,b'\x10'*6),(1,b'\x10'*3+b'\0'*3),(2,b'\x10'*6),(3,b'\x10'*3+b'\x08'*3),(4,b'\x10'*3+b'\0'*3)]:
            self.assertEqual(decode(self.png(2,bytes([method])+raw))[2],b'\x10\x10\x10\xff'*2)
    def test_reject_bad_and_unsupported_pngs(self):
        data=encode(2,1,b'\0'*8)
        for bad in (data[:-1],data+b'x',data[:30]+b'x'+data[31:],self.png(6,b'\0'+b'\0'*8,depth=16),self.png(6,b'\0'+b'\0'*8,interlace=1),self.png(6,b'\5'+b'\0'*8),self.png(6,b'\0'+b'\0'*9),self.png(3,b'\0\0\0')):
            with self.subTest(size=len(bad)):
                with self.assertRaises(ArtError):decode(bad)


if __name__=='__main__':unittest.main()

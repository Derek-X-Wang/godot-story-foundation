import tempfile,unittest,json
from pathlib import Path
from PIL import Image
from check import check,LAYERS
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
  for name in LAYERS:
   im=Image.new('RGBA',(8,12));im.putpixel((4,6),(80,90,100,255));im.save(self.p/(name+'.png'))
  (self.p/'config.json').write_text('{"width":8}')
  (self.p/'iris-layer.png.import').write_text('[params]\nprocess/fix_alpha_border=false\nprocess/premult_alpha=false\n')
 def tearDown(self):self.tmp.cleanup()
 def test_valid(self):self.assertTrue(check(self.p)['passed'])
 def test_missing(self):
  (self.p/'half.png').unlink();self.assertFalse(check(self.p)['passed'])
 def test_opaque(self):
  Image.new('RGBA',(8,12),'white').save(self.p/'base.png');self.assertFalse(check(self.p)['passed'])
 def test_size(self):
  Image.new('RGBA',(9,12)).save(self.p/'closed.png');self.assertFalse(check(self.p)['passed'])
 def test_empty_iris(self):
  Image.new('RGBA',(8,12)).save(self.p/'iris-layer.png');self.assertFalse(check(self.p)['passed'])
 def test_import(self):
  (self.p/'iris-layer.png.import').write_text('[params]\nprocess/fix_alpha_border=true');self.assertFalse(check(self.p)['passed'])
 def test_commented_setting(self):
  (self.p/'iris-layer.png.import').write_text('[params]\n# process/fix_alpha_border=false\nprocess/fix_alpha_border=true\nprocess/premult_alpha=false');self.assertFalse(check(self.p)['passed'])
 def test_duplicate_setting(self):
  (self.p/'iris-layer.png.import').write_text('[params]\nprocess/fix_alpha_border=false\nprocess/fix_alpha_border=true\nprocess/premult_alpha=false');self.assertFalse(check(self.p)['passed'])
 def test_config(self):
  (self.p/'config.json').write_text('[]');self.assertFalse(check(self.p)['passed'])

class ReliabilityTests(unittest.TestCase):
 setUp=Tests.setUp
 tearDown=Tests.tearDown
 def test_invalid_utf8_config(self):
  (self.p/'config.json').write_bytes(b'\xff');self.assertFalse(check(self.p)['passed'])
 def test_wrong_image_format(self):
  Image.new('RGB',(8,12),'white').save(self.p/'half.png',format='JPEG');self.assertFalse(check(self.p)['passed'])
 def test_gate_runs_only_valid(self):
  import subprocess,sys
  marker=self.p/'exported'
  cmd=[sys.executable,str(Path(__file__).with_name('gate.py')),str(self.p),'--',sys.executable,'-c',f'from pathlib import Path; Path({str(marker)!r}).touch()']
  good=subprocess.run(cmd,capture_output=True);self.assertEqual(good.returncode,0);self.assertTrue(marker.exists())
  marker.unlink();(self.p/'config.json').write_bytes(b'\xff')
  bad=subprocess.run(cmd,capture_output=True);self.assertEqual(bad.returncode,1);self.assertFalse(marker.exists());self.assertIsInstance(json.loads(bad.stdout),list)
 def test_gate_propagates_failure(self):
  import subprocess,sys
  result=subprocess.run([sys.executable,str(Path(__file__).with_name('gate.py')),str(self.p),'--',sys.executable,'-c','raise SystemExit(7)'],capture_output=True)
  self.assertEqual(result.returncode,7)
 def test_gate_no_command(self):
  import subprocess,sys
  result=subprocess.run([sys.executable,str(Path(__file__).with_name('gate.py')),str(self.p),'--'],capture_output=True)
  self.assertEqual(result.returncode,2)
 def test_batch_continues_after_corrupt_config(self):
  import subprocess,sys
  other=self.p/'missing'
  (self.p/'config.json').write_bytes(b'\xff')
  result=subprocess.run([sys.executable,str(Path(__file__).with_name('check.py')),str(self.p),str(other)],capture_output=True)
  self.assertEqual(result.returncode,1);self.assertEqual(len(json.loads(result.stdout)),2)

 def test_gate_mixed_batch_blocks_export(self):
  import subprocess,sys
  marker=self.p/'exported'
  result=subprocess.run([sys.executable,str(Path(__file__).with_name('gate.py')),str(self.p),str(self.p/'missing'),'--',sys.executable,'-c',f'from pathlib import Path; Path({str(marker)!r}).touch()'],capture_output=True)
  self.assertEqual(result.returncode,1);self.assertFalse(marker.exists())
  self.assertEqual([x['passed'] for x in json.loads(result.stdout)],[True,False])
 def test_gate_missing_executable(self):
  import subprocess,sys
  result=subprocess.run([sys.executable,str(Path(__file__).with_name('gate.py')),str(self.p),'--',str(self.p/'no-such-executable')],capture_output=True)
  self.assertEqual(result.returncode,127)
 def test_gate_signal_exit(self):
  import subprocess,sys
  result=subprocess.run([sys.executable,str(Path(__file__).with_name('gate.py')),str(self.p),'--',sys.executable,'-c','import os,signal; os.kill(os.getpid(),signal.SIGTERM)'],capture_output=True)
  self.assertEqual(result.returncode,143)

 def test_wrong_import_section(self):
  (self.p/'iris-layer.png.import').write_text('[remap]\nprocess/fix_alpha_border=false\nprocess/premult_alpha=false\n[params]\nprocess/fix_alpha_border=true\nprocess/premult_alpha=true\n')
  self.assertFalse(check(self.p)['passed'])

if __name__=='__main__':unittest.main()

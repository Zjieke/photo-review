import contextlib,io,json,random,tempfile,unittest
from pathlib import Path
from PIL import Image,ImageDraw
import find_photo_duplicates as m
class DuplicateTests(unittest.TestCase):
 def test_original_bytes_and_cloud_preview_never_equated(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);work=root/'work';out=root/'outputs';work.mkdir();out.mkdir();(out/'previews').mkdir();(out/'delete-receipts').mkdir()
   image=Image.new('RGB',(120,80));rng=random.Random(2);image.putdata([(rng.randrange(255),rng.randrange(255),rng.randrange(255)) for _ in range(9600)])
   original=root/'one.png';image.save(original);copy=root/'two.png';copy.write_bytes(original.read_bytes())
   rows=[];inventory=[]
   for i,path in enumerate([original,copy,root/'missing.png']):
    u=str(i);image.save(out/f'previews/{u}.jpg');rows.append({'uuid':u,'thumbnail':f'previews/{u}.jpg','original':str(path),'filename':f'{i}.png','date':'2026-10-22T00:00:00','favorite':False});inventory.append({'uuid':u,'bytes':100})
   (out/'full_results.json').write_text(json.dumps(rows));(work/'activity_inventory.json').write_text(json.dumps({'items':inventory}))
   previous=m.WORK,m.OUT;m.WORK,m.OUT=work,out
   try:
    with contextlib.redirect_stdout(io.StringIO()):m.run()
    result=json.loads((out/'duplicate_groups.json').read_text());exact=[g for g in result['groups'] if g['kind']=='exact'];self.assertEqual(len(exact),1);self.assertEqual({r['uuid'] for r in exact[0]['items']},{'0','1'});self.assertEqual(result['original_available'],2)
   finally:m.WORK,m.OUT=previous
 def test_tree_matches_bruteforce(self):
  t=m.Tree();values=[random.Random(i).getrandbits(64) for i in range(200)]
  for i,h in enumerate(values):t.add(h,str(i))
  for h in values[:10]:self.assertEqual(set(t.search(h)),{str(i) for i,x in enumerate(values) if (h^x).bit_count()<=5})
 def test_uniform_images_not_similar(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'blank.jpg';Image.new('RGB',(80,80),'white').save(p);self.assertIsNone(m.visual(p))
if __name__=='__main__':unittest.main()

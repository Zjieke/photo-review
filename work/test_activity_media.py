import unittest,threading,tempfile,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import review_server as server
class ActivityMediaTests(unittest.TestCase):
 def test_ranges(self):
  self.assertEqual(server.media_range('bytes=2-5',10),(2,5,206))
  self.assertEqual(server.media_range('bytes=-4',10),(6,9,206))
  self.assertEqual(server.media_range('bytes=7-',10),(7,9,206))
  self.assertEqual(server.media_range(None,10),(0,9,200))
  for h in ['bytes=10-','bytes=5-2','bytes=0-1,3-4','bytes=-0','bad']:
   with self.assertRaises(ValueError):server.media_range(h,10)
 def test_only_allowlisted_video_streams(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'movie.mov';p.write_bytes(b'0123456789')
   with patch.object(server,'ACTIVITY_MEDIA',{'video-id':{'kind':'video','path':str(p)},'photo-id':{'kind':'photo','path':str(p)}}),patch.object(server,'receipts',return_value=[]):
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
     host=f'127.0.0.1:{http.server_port}'
     req=urllib.request.Request(f'http://{host}/api/activity-media/video-id',headers={'Host':host,'Range':'bytes=2-5'})
     with urllib.request.urlopen(req) as r:self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345');self.assertEqual(r.headers['Content-Range'],'bytes 2-5/10')
     for key in ['photo-id','not-registered','..%2Fsecret']:
      req=urllib.request.Request(f'http://{host}/api/activity-media/{key}',headers={'Host':host})
      with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
      self.assertEqual(e.exception.code,404)
      e.exception.close()
     for invalid_host in ['attacker.invalid','127.0.0.1:8768']:
      req=urllib.request.Request(f'http://{host}/api/activity-media/video-id',headers={'Host':invalid_host})
      with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
      self.assertEqual(e.exception.code,403)
      e.exception.close()
    finally:http.shutdown();http.server_close()
if __name__=='__main__':unittest.main()

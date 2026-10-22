import json
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import review_server as server

PHOTO_ID='00000000-0000-0000-0000-000000000001'
ACTIVITY_PHOTO_ID='00000000-0000-0000-0000-000000000002'
VIDEO_ID='00000000-0000-0000-0000-000000000003'
PROTECTED_ID='00000000-0000-0000-0000-000000000004'

class AllowedAssetTests(unittest.TestCase):
    def test_activity_photos_and_videos_extend_label_inventory(self):
        allowed=server.allowed_asset_ids(
            [{'uuid':PHOTO_ID,'deletable':True}],
            [{'uuid':ACTIVITY_PHOTO_ID,'kind':'photo','favorite':False},
             {'uuid':VIDEO_ID,'kind':'video','available':False},
             {'uuid':'audio-id','kind':'audio'},
             {'uuid':'missing-kind'}, {'kind':'video'}])
        self.assertEqual(allowed,{PHOTO_ID,ACTIVITY_PHOTO_ID,VIDEO_ID})

    def test_protection_in_either_inventory_wins(self):
        for protection in ({'favorite':True},{'hidden':True},{'deletable':False}):
            for protected_source in ('labels','activities'):
                with self.subTest(protection=protection,source=protected_source):
                    label={'uuid':PHOTO_ID,'deletable':True}
                    activity={'uuid':PHOTO_ID,'kind':'photo','deletable':True}
                    (label if protected_source=='labels' else activity).update(protection)
                    self.assertEqual(server.allowed_asset_ids([label],[activity]),set())

    def test_existing_activity_favorites_remain_protected(self):
        self.assertEqual(server.allowed_asset_ids([], [
            {'uuid':ACTIVITY_PHOTO_ID,'kind':'photo','favorite':False},
            {'uuid':VIDEO_ID,'kind':'video','favorite':True},
        ]),{ACTIVITY_PHOTO_ID})

    def test_duplicate_rows_cannot_override_protection(self):
        rows=[{'uuid':PHOTO_ID,'deletable':False},{'uuid':PHOTO_ID,'deletable':True}]
        self.assertEqual(server.allowed_asset_ids(rows,[]),set())

class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(server,'JOURNAL',Path(self.temp.name));self.patch.start();self.addCleanup(self.patch.stop)
        self.ids=[PHOTO_ID,ACTIVITY_PHOTO_ID,VIDEO_ID]
        allowed=server.allowed_asset_ids(
            [{'uuid':PHOTO_ID,'deletable':True}],
            [{'uuid':ACTIVITY_PHOTO_ID,'kind':'photo'},
             {'uuid':VIDEO_ID,'kind':'video','available':False},
             {'uuid':PROTECTED_ID,'kind':'video','favorite':True}])
        allow_patch=patch.object(server,'ALLOWED',allowed);allow_patch.start();self.addCleanup(allow_patch.stop)
        self.request={'requestId':'11111111-1111-1111-1111-111111111111','uuids':self.ids,'confirmed':True}
    def test_mixed_media_success_and_idempotence(self):
        calls=[]
        def native(action,ids):
            calls.append((action,ids));return {'ok':True,'deleted':ids} if action=='trash' else {'ok':True}
        first=server.trash(self.request,native)
        self.assertTrue(first['ok']);self.assertEqual(first['deleted'],sorted(self.ids))
        self.assertEqual(server.trash(self.request,native),first)
        self.assertEqual(calls,[('check',sorted(self.ids)),('trash',sorted(self.ids))])
        self.assertEqual(server.receipts()[0]['state'],'done')
    def test_missing_confirmation_and_outside_allowlist(self):
        for change in ({'confirmed':False},{'uuids':['outside']},{'uuids':[self.ids[0]]*2},{'uuids':[]},
                       {'uuids':[PROTECTED_ID]}, {'uuids':['00000000-0000-0000-0000-000000000099']}):
            with self.assertRaises(ValueError): server.trash(self.request|change,lambda *args:self.fail('native called'))
    def test_batch_limit_still_applies_to_all_media(self):
        ids=[f'00000000-0000-0000-0000-{index:012d}' for index in range(121)]
        with patch.object(server,'ALLOWED',set(ids)):
            self.assertEqual(server.validate_ids(ids[:120]),sorted(ids[:120]))
            with self.assertRaises(ValueError):server.validate_ids(ids)
    def test_permission_or_preflight_failure_never_deletes(self):
        calls=[]
        def native(action,ids): calls.append(action);return {'ok':False,'error':'missing permissions'}
        self.assertFalse(server.trash(self.request,native)['ok']);self.assertEqual(calls,['check'])
    def test_uncertain_result_blocks_repeat(self):
        def native(action,ids):
            if action=='trash':raise TimeoutError()
            return {'ok':True}
        self.assertTrue(server.trash(self.request,native)['uncertain'])
        with self.assertRaises(ValueError):server.trash(self.request|{'requestId':'22222222-2222-2222-2222-222222222222'},native)
    def test_id_reuse_cannot_change_selection(self):
        server.trash(self.request,lambda action,ids:{'ok':True,'deleted':ids})
        with self.assertRaises(ValueError):server.trash(self.request|{'uuids':self.ids[:1]})
    def test_native_mismatched_result_is_not_success(self):
        result=server.trash(self.request,lambda action,ids:{'ok':True,'deleted':[]} if action=='trash' else {'ok':True})
        self.assertTrue(result['uncertain']);self.assertFalse(result['ok'])

class RemovedCollaborationRoutesTests(unittest.TestCase):
    def setUp(self):
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.url=f'http://127.0.0.1:{self.http.server_port}'

    def test_removed_routes_cannot_serve_models_images_or_accept_tasks(self):
        routes=[
            ('GET','/api/cluster/status'),('GET','/api/worker/manifest'),
            ('GET','/api/worker/model?name=model.safetensors'),
            ('GET','/api/worker/image?uuid=test'),
            ('GET','/Qwen%E5%8D%8F%E4%BD%9C%E5%8A%A9%E6%89%8B-Mac-Apple%E8%8A%AF%E7%89%87.zip'),
            ('POST','/api/worker/claim'),('POST','/api/worker/result'),
            ('POST','/api/worker/heartbeat'),('POST','/api/cluster/configure'),
        ]
        with patch.object(server,'native',side_effect=AssertionError('native must not run')):
            for method,path in routes:
                with self.subTest(path=path):
                    request=urllib.request.Request(self.url+path,method=method,
                        data=b'{}' if method=='POST' else None,
                        headers={'Host':f'127.0.0.1:{self.http.server_port}','Origin':self.url,
                                 'X-Review-Token':server.TOKEN,'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request,timeout=3)
                    self.assertEqual(error.exception.code,404)
                    error.exception.close()

    def test_host_and_origin_must_match_actual_port(self):
        for headers in (
            {'Host':'attacker.invalid'},
            {'Host':'127.0.0.1:8768'},
            {'Origin':'http://attacker.invalid','X-Review-Token':server.TOKEN},
            {'Origin':self.url,'X-Review-Token':'wrong-token'},
            {'Origin':self.url},
        ):
            request=urllib.request.Request(self.url+'/api/trash',method='POST',data=b'{}',
                                          headers={'Content-Type':'application/json',**headers})
            with patch.object(server,'trash',side_effect=AssertionError('must reject before deletion')):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request,timeout=3)
                self.assertEqual(error.exception.code,403)
                error.exception.close()

    def test_empty_inventory_cannot_delete_any_identifier(self):
        with patch.object(server,'ALLOWED',set()):
            request=urllib.request.Request(self.url+'/api/trash',method='POST',
                data=json.dumps({'uuids':[PHOTO_ID],'confirmed':True,
                                 'requestId':'11111111-1111-1111-1111-111111111111'}).encode(),
                headers={'Origin':self.url,'X-Review-Token':server.TOKEN,'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request,timeout=3)
            self.assertEqual(error.exception.code,400)
            error.exception.close()

if __name__=='__main__':unittest.main()

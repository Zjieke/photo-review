"""Synthetic folder scan and deletion boundaries, portable on all CI platforms."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from folder_library import save_folder, media_files, native, signature
from folder_analysis import scan
from model_manager import atomic_json


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.photos = self.root/'照片'; self.photos.mkdir()
        self.data = self.root/'data'; self.state = self.data/'work'; self.state.mkdir(parents=True)
        self.output = self.data/'outputs'; self.output.mkdir()
        self.picture = self.photos/'screenshot.png'; Image.new('RGB',(80,50),'green').save(self.picture)
        save_folder(self.photos,self.state)

    def test_scan_reuses_ocr_and_keeps_ids_and_activity_sizes(self):
        ocr = Mock(return_value=('订单详情','complete'))
        scan(output=self.output,state=self.state,ocr=ocr)
        first = json.loads((self.output/'full_results.json').read_text(encoding='utf-8'))
        scan(output=self.output,state=self.state,ocr=ocr)
        second = json.loads((self.output/'full_results.json').read_text(encoding='utf-8'))
        self.assertEqual(first,second); self.assertEqual(ocr.call_count,1)
        self.assertTrue(second[0]['screenshot']); self.assertEqual(second[0]['ocr'],'订单详情')
        activity=json.loads((self.state/'activity_inventory.json').read_text(encoding='utf-8'))['items']
        self.assertEqual(activity[0]['bytes'],self.picture.stat().st_size)
        self.assertTrue((self.output/second[0]['thumbnail']).is_file())

    def test_recycler_is_only_called_for_unchanged_scanned_media(self):
        identifier='synthetic'
        atomic_json(self.state/'folder-file-index.json',{identifier:{'path':str(self.picture),'root':str(self.photos),'signature':signature(self.picture)}})
        recycler=Mock()
        self.assertTrue(native('check',[identifier],state=self.state)['ok'])
        result=native('trash',[identifier],state=self.state,recycler=recycler)
        self.assertEqual(result['deleted'],[identifier]); recycler.assert_called_once_with([str(self.picture)])
        self.assertTrue(self.picture.exists(),'mocked deletion must not remove test input')
        self.picture.write_bytes(b'changed')
        self.assertFalse(native('trash',[identifier],state=self.state,recycler=recycler)['ok'])
        self.assertEqual(recycler.call_count,1)
        self.assertFalse(native('trash',['unknown'],state=self.state,recycler=recycler)['ok'])

    def test_outside_root_and_links_are_rejected(self):
        outside=self.root/'outside.png'; Image.new('RGB',(20,20)).save(outside)
        atomic_json(self.state/'folder-file-index.json',{'outside':{'path':str(outside),'root':str(self.photos),'signature':signature(outside)}})
        recycler=Mock(); self.assertFalse(native('trash',['outside'],state=self.state,recycler=recycler)['ok']);recycler.assert_not_called()
        try:(self.photos/'link.png').symlink_to(outside)
        except OSError:return
        self.assertFalse(dict(media_files(self.photos))[self.photos/'link.png'])

    def test_cannot_select_entire_drive_or_parent_of_app_data(self):
        with self.assertRaises(ValueError):save_folder(Path(self.root.anchor),self.state)
        with self.assertRaises(ValueError):save_folder(self.root,self.state)

    def test_unavailable_ocr_is_retried_and_replacement_file_gets_new_identity(self):
        ocr=Mock(side_effect=[('', 'unavailable'), ('PHOTO','complete'), ('NEW','complete')])
        scan(output=self.output,state=self.state,ocr=ocr)
        scan(output=self.output,state=self.state,ocr=ocr)
        self.assertEqual(ocr.call_count,2)
        old=json.loads((self.output/'full_results.json').read_text(encoding='utf-8'))[0]['uuid']
        replacement=self.photos/'new.png'; Image.new('RGB',(90,60),'blue').save(replacement)
        replacement.replace(self.picture)
        scan(output=self.output,state=self.state,ocr=ocr)
        new=json.loads((self.output/'full_results.json').read_text(encoding='utf-8'))[0]['uuid']
        self.assertNotEqual(old,new)


if __name__=='__main__':unittest.main()

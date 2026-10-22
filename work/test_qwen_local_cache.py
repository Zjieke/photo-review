import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from qwen_local_cache import acquire_job_lock, initialize_cache, pending_ids, save_result


class LocalCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'cache.sqlite3'
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        initialize_cache(self.db)

    def test_existing_success_survives_restart_and_later_writes(self):
        original = {'status': 'complete', 'topic': ['生活记录']}
        save_result(self.db, 'done', 'v1', original, seconds=2)
        save_result(self.db, 'done', 'v1', {'status': 'complete', 'topic': ['购物']})
        save_result(self.db, 'done', 'v1', error='interrupted')
        with sqlite3.connect(self.path) as reopened:
            self.assertEqual(pending_ids(reopened, ['done', 'new'], 'v1'), ['new'])
            self.assertEqual(json.loads(reopened.execute('SELECT data FROM results').fetchone()[0]), original)

    def test_failed_and_interrupted_items_remain_pending(self):
        save_result(self.db, 'failed', 'v1', error='decode failed')
        self.assertEqual(pending_ids(self.db, ['failed', 'unfinished', 'failed'], 'v1'), ['failed', 'unfinished'])
        save_result(self.db, 'failed', 'v1', {'status': 'complete'})
        self.assertEqual(pending_ids(self.db, ['failed', 'unfinished'], 'v1'), ['unfinished'])

    def test_new_version_does_not_reuse_old_success(self):
        save_result(self.db, 'asset', 'v1', {'status': 'complete'})
        self.assertEqual(pending_ids(self.db, ['asset'], 'v2'), ['asset'])
        save_result(self.db, 'asset', 'v2', {'status': 'complete', 'topic': ['餐饮']})
        self.assertEqual({row[0] for row in self.db.execute('SELECT version FROM results')}, {'v1', 'v2'})

    def test_failed_new_model_preserves_older_success(self):
        original = {'status': 'complete', 'topic': ['生活记录']}
        save_result(self.db, 'asset', 'model-a', original)
        save_result(self.db, 'asset', 'model-b', error='model b failed')
        rows = {version: (status, json.loads(data)) for version, status, data in
                self.db.execute('SELECT version,status,data FROM results WHERE uuid=?', ('asset',))}
        self.assertEqual(rows['model-a'], ('complete', original))
        self.assertEqual(rows['model-b'][0], 'failed')
        self.assertEqual(pending_ids(self.db, ['asset'], 'model-a'), [])
        self.assertEqual(pending_ids(self.db, ['asset'], 'model-b'), ['asset'])

    def test_migration_keeps_every_legacy_record_and_is_repeatable(self):
        self.db.execute('DROP TABLE results')
        self.db.execute('CREATE TABLE results(uuid TEXT PRIMARY KEY,version TEXT,status TEXT,data TEXT,seconds REAL,error TEXT)')
        records = [('done', 'v1', 'complete', json.dumps({'status': 'complete'}), 2.5, ''),
                   ('failed', 'v1', 'failed', '{}', 1.1, 'decode failed')]
        self.db.executemany('INSERT INTO results VALUES(?,?,?,?,?,?)', records)
        self.db.commit()
        initialize_cache(self.db)
        initialize_cache(self.db)
        self.assertEqual(self.db.execute('SELECT * FROM results ORDER BY uuid').fetchall(), records)
        primary_key = {row[1]: row[5] for row in self.db.execute('PRAGMA table_info(results)')}
        self.assertEqual((primary_key['uuid'], primary_key['version']), (1, 2))
        save_result(self.db, 'done', 'v2', error='new version failed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM results').fetchone()[0], 3)

    def test_invalid_result_is_not_committed(self):
        with self.assertRaises(ValueError):
            save_result(self.db, 'asset', 'v1', {'status': 'unknown'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM results').fetchone()[0], 0)

    def test_only_one_local_job_can_hold_lock(self):
        path = Path(self.temp.name) / 'job.lock'
        handle = acquire_job_lock(path)
        try:
            with self.assertRaises(RuntimeError):
                acquire_job_lock(path)
        finally:
            handle.close()
        acquire_job_lock(path).close()


if __name__ == '__main__':
    unittest.main()

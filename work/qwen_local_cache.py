"""Checkpoint helpers for a single local image-recognition process."""
from file_lock import lock
import json


def acquire_job_lock(path):
    handle = path.open('a+b')
    try:
        lock(handle)
    except BlockingIOError:
        handle.close()
        raise RuntimeError('本地识别任务已在运行') from None
    return handle


def initialize_cache(connection):
    """Keep each model version independently; migrate the original UUID-only table atomically."""
    columns = connection.execute('PRAGMA table_info(results)').fetchall()
    schema = '''CREATE TABLE results(
        uuid TEXT NOT NULL, version TEXT NOT NULL, status TEXT, data TEXT, seconds REAL, error TEXT,
        PRIMARY KEY(uuid, version))'''
    if not columns:
        connection.execute(schema)
        return
    primary_key = [column[1] for column in sorted(columns, key=lambda column: column[5]) if column[5]]
    if primary_key == ['uuid', 'version']:
        return
    if primary_key != ['uuid'] or [column[1] for column in columns] != ['uuid', 'version', 'status', 'data', 'seconds', 'error']:
        raise RuntimeError('本地识别缓存结构不兼容，已停止，未改写缓存。')
    connection.execute('SAVEPOINT migrate_qwen_cache')
    try:
        connection.execute('ALTER TABLE results RENAME TO results_legacy_migration')
        connection.execute(schema)
        connection.execute('INSERT INTO results SELECT uuid,version,status,data,seconds,error FROM results_legacy_migration')
        connection.execute('DROP TABLE results_legacy_migration')
        connection.execute('RELEASE SAVEPOINT migrate_qwen_cache')
    except Exception:
        connection.execute('ROLLBACK TO SAVEPOINT migrate_qwen_cache')
        connection.execute('RELEASE SAVEPOINT migrate_qwen_cache')
        raise


def pending_ids(connection, ids, version):
    completed = {
        row[0] for row in connection.execute(
            "SELECT uuid FROM results WHERE version=? AND status='complete'",
            (version,),
        )
    }
    return [identifier for identifier in dict.fromkeys(ids) if identifier not in completed]


def save_result(connection, identifier, version, result=None, error='', seconds=0):
    if result is not None and (
        not isinstance(result, dict) or result.get('status') != 'complete'
    ):
        raise ValueError('识别结果格式无效')
    status = 'complete' if result is not None else 'failed'
    data = json.dumps(result or {}, ensure_ascii=False)
    with connection:
        connection.execute(
            """INSERT INTO results VALUES(?,?,?,?,?,?)
            ON CONFLICT(uuid, version) DO UPDATE SET
                status=excluded.status,
                data=excluded.data, seconds=excluded.seconds, error=excluded.error
            WHERE results.status!='complete'""",
            (identifier, version, status, data, max(0, float(seconds)), str(error)[:160]),
        )

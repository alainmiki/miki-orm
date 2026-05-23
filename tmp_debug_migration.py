import tempfile
import mikiorm
from mikiorm import models
from mikiorm.migrations.engine import MigrationEngine
from mikiorm.models.fields import CharField
from mikiorm.settings import connection_manager

TMP = tempfile.mkdtemp()
print('tmp', TMP)
mikiorm.configure({'default': {'ENGINE': 'sqlite', 'NAME': ':memory:', 'POOL': {'min_size': 1, 'max_size': 1, 'timeout': 5}}})

class MigrationTestModel(models.Model):
    name = CharField(max_length=20)

    class Meta:
        table_name = 'migration_test_model'

engine = MigrationEngine(migrations_path=TMP)
ops = engine.makemigrations([MigrationTestModel])
print('ops', len(ops), [op.operation_type for op in ops])
history_map = engine._build_migration_map()
print('history_map', history_map)
migration_name, migration_filepath = next(iter(history_map.items()))
print('migration_filepath', migration_filepath)
conn = connection_manager.get_connection('default')
print('conn acquired type', type(conn), 'underlying', type(conn.raw))
engine.migrate_direct(str(migration_filepath), connection=conn)
print('applied first')
cur = conn.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', ('migration_test_model',))
print('table exists after apply', cur.fetchall())
conn.close()
conn2 = connection_manager.get_connection('default')
print('conn2 acquired type', type(conn2), 'underlying', type(conn2.raw))
cur2 = conn2.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', ('migration_test_model',))
print('table exists after reopen', cur2.fetchall())
conn2.close()
print('done')

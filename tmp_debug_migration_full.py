import tempfile
import mikiorm
from mikiorm import models
from mikiorm.migrations.engine import MigrationEngine
from mikiorm.models.fields import CharField, IntegerField
from mikiorm.migrations.operations import AddField, AlterField, RemoveField
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
conn = connection_manager.get_connection('default')
print('conn re-acquired', type(conn), 'underlying', type(conn.raw))
cur = conn.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', ('migration_test_model',))
print('table exists after re-acquire', cur.fetchall())

age_field = IntegerField(default=0)
age_field.name = 'age'
add_field = AddField('migration_test_model', age_field)
alter_field = AlterField('migration_test_model', age_field)
drop_field = RemoveField('migration_test_model', 'age')
migration_file = TMP + '/0002_auto.py'
engine._write_migration_file(migration_file, [add_field, alter_field, drop_field])
print('wrote second migration', migration_file)
engine.migrate_direct(migration_file, connection=conn)
print('applied second migration')
cur = conn.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name=?', ('migration_test_model',))
print('table sql', cur.fetchall())
conn.close()
print('done')

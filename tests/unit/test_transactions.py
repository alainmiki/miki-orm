"""Transaction handling: sync atomic and async_atomic, unit of work, rollback, nesting."""

import pytest

from myorm import atomic, async_atomic, configure, settings
from myorm.models.base import Model
from myorm.models.fields import AutoField, BooleanField, CharField, IntegerField, ForeignKey
from myorm.models.relationships import CASCADE


class Item(Model):
    name = CharField(max_length=50)

    class Meta:
        table_name = "txn_items"


class Container(Model):
    name = CharField(max_length=50)
    item = ForeignKey(Item, on_delete=CASCADE, related_name="containers")

    class Meta:
        table_name = "txn_containers"


def db_config(backend):
    if backend == "sqlite":
        return {"ENGINE": "sqlite", "NAME": ":memory:"}
    elif backend == "postgres":
        return {
            "ENGINE": "postgresql",
            "NAME": "miki_orm_test",
            "USER": "postgres",
            "PASSWORD": "admin",
            "HOST": "localhost",
            "PORT": 5432,
        }


@pytest.fixture(scope="module", params=["sqlite", "postgres"])
def backend(request):
    backend = request.param
    configure(databases={"default": db_config(backend)})
    yield backend
    settings.connection_manager.close_all()


@pytest.fixture(autouse=True)
def setup_db(backend):
    for m in [Item, Container]:
        m._table_created = False
        dummy = m()
        for fname, fobj in m._meta.fields.items():
            if not fobj.null and not isinstance(fobj, AutoField):
                if isinstance(fobj, CharField):
                    setattr(dummy, fname, "x")
                elif isinstance(fobj, IntegerField):
                    setattr(dummy, fname, 0)
                else:
                    setattr(dummy, fname, None)
        try:
            dummy.save(force_insert=True)
        except Exception:
            pass

    yield

    for m in [Item, Container]:
        try:
            conn = settings.connection_manager.get_connection()
            conn.execute(f"DELETE FROM {m._meta.table_name}", ())
            conn.commit()
        except Exception:
            pass


from myorm.models.fields import AutoField  # noqa: E402


def test_atomic_commit(backend):
    """Successful atomic block commits all changes."""
    with atomic():
        Item.objects.create(name="item1")
        Item.objects.create(name="item2")
    assert Item.objects.count() == 2


def test_atomic_rollback(backend):
    """Exception in atomic block rolls back all changes."""
    initial = Item.objects.count()
    try:
        with atomic():
            Item.objects.create(name="item3")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass
    assert Item.objects.count() == initial


def test_nested_atomic_blocks(backend):
    """Nested atomic blocks should work (begin may be no-op if already in tx)."""
    with atomic():
        Item.objects.create(name="outer")
        with atomic():
            Item.objects.create(name="inner")
    assert Item.objects.count() == 2


def test_foreign_key_operations_in_transaction(backend):
    """FK-related objects saved inside atomic respect on_delete."""
    with atomic():
        i1 = Item.objects.create(name="item1")
        i2 = Item.objects.create(name="item2")
        c = Container.objects.create(name="cont", item=i1)
        # Deleting i1 should cascade to container
        i1.delete()
    # After commit, container should be gone
    assert Container.objects.count() == 0
    # i2 should still exist
    assert Item.objects.count() == 1


@pytest.mark.asyncio
async def test_async_atomic_commit(backend):
    """Async atomic commits on success."""
    async with async_atomic():
        await Item.async_create(name="async_item1")
        await Item.async_create(name="async_item2")
    assert await Item.objects.async_count() == 2


@pytest.mark.asyncio
async def test_async_atomic_rollback(backend):
    """Async atomic rolls back on exception."""
    initial = await Item.objects.async_count()
    try:
        async with async_atomic():
            await Item.async_create(name="bad_async")
            raise RuntimeError("async rollback")
    except RuntimeError:
        pass
    assert await Item.objects.async_count() == initial


@pytest.mark.asyncio
async def test_async_save_inside_transaction(backend):
    """async_save inside async_atomic defers until commit."""
    async with async_atomic():
        item = Item(name="deferred")
        await item.async_save()
        # Not visible outside the transaction yet
    # After commit, visible
    assert await Item.objects.async_filter(name="deferred").async_count() == 1


def test_unit_of_work_tracks_objects(backend):
    """UnitOfWorkTracker registers new, dirty, deleted instances."""
    from myorm.unit_of_work.transaction import TransactionManager

    tx_mgr = TransactionManager(settings.connection_manager.get_connection())
    with tx_mgr:
        # New object
        i = Item(name="tracked_new")
        tx_mgr.tracker.register_new(i)
        # Dirty object
        fetched = Item.objects.create(name="tracked_dirty")
        fetched.name = "changed"
        tx_mgr.tracker.register_dirty(fetched)
        # Deleted
        to_delete = Item.objects.create(name="tracked_deleted")
        tx_mgr.tracker.register_deleted(to_delete)
        assert len(tx_mgr.tracker.new) == 1
        assert len(tx_mgr.tracker.dirty) == 1
        assert len(tx_mgr.tracker.deleted) == 1
        # commit function is available but not called yet
        assert hasattr(tx_mgr.commit_manager, "commit")

"""Async tests: async queryset, async save/delete, async transactions."""

import asyncio

import pytest

from mikiorm import async_atomic, configure, settings
from mikiorm.models.base import Model
from mikiorm.models.fields import AutoField, BooleanField, CharField, IntegerField, ForeignKey
from mikiorm.models.relationships import CASCADE


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AsyncItem(Model):
    name = CharField(max_length=50)
    value = IntegerField(default=0)

    class Meta:
        table_name = "async_items"


class AsyncAuthor(Model):
    name = CharField(max_length=50)
    email = CharField(max_length=100, unique=True)

    class Meta:
        table_name = "async_authors"


class AsyncPost(Model):
    title = CharField(max_length=100)
    author = ForeignKey(AsyncAuthor, on_delete=CASCADE, related_name="posts")

    class Meta:
        table_name = "async_posts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def get_config(backend):
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
    else:
        raise ValueError(backend)


@pytest.fixture(scope="module", params=["sqlite", "postgres"])
async def backend(request):
    backend = request.param
    configure(databases={"default": get_config(backend)})
    yield backend
    try:
        settings.connection_manager.close_all()
        await settings.async_connection_manager.close_all()
    except Exception:
        pass


@pytest.fixture(autouse=True)
async def clean_db(backend):
    for m in [AsyncItem, AsyncAuthor, AsyncPost]:
        m._table_created = False
        dummy = m()
        for fname, fobj in m._meta.fields.items():
            if not fobj.null and not isinstance(fobj, AutoField):
                if isinstance(fobj, CharField):
                    setattr(dummy, fname, "x")
                elif isinstance(fobj, IntegerField):
                    setattr(dummy, fname, 0)
                elif isinstance(fobj, BooleanField):
                    setattr(dummy, fname, True)
                else:
                    setattr(dummy, fname, None)
        try:
            dummy.save(force_insert=True)
        except Exception:
            pass

    yield

    for m in [AsyncItem, AsyncAuthor, AsyncPost]:
        try:
            conn = settings.connection_manager.get_connection()
            conn.execute(f"DELETE FROM {m._meta.table_name}", ())
            conn.commit()
        except Exception:
            pass
        try:
            aconn = await settings.async_connection_manager.get_connection()
            await aconn.execute(f"DELETE FROM {m._meta.table_name}", ())
            await aconn.commit()
        except Exception:
            pass


from mikiorm.models.fields import AutoField, BooleanField, TextField  # noqa: E402, F401


@pytest.mark.asyncio
async def test_async_create_and_get(backend):
    async with async_atomic():
        author = await AsyncAuthor.async_create(name="AsyncAuth", email="async@example.com")
        assert author.pk is not None
        assert author.name == "AsyncAuth"

    fetched = await AsyncAuthor.objects.async_get(pk=author.pk)
    assert fetched.name == "AsyncAuth"


@pytest.mark.asyncio
async def test_async_update(backend):
    async with async_atomic():
        item = await AsyncItem.async_create(name="Item1", value=10)
    await item.async_save()
    item.value = 20
    await item.async_save()

    fetched = await AsyncItem.objects.async_get(pk=item.pk)
    assert fetched.value == 20


@pytest.mark.asyncio
async def test_async_delete(backend):
    async with async_atomic():
        item = await AsyncItem.async_create(name="ToDelete", value=5)
    pk = item.pk
    await item.async_delete()
    assert await AsyncItem.objects.async_filter(pk=pk).async_exists() is False


@pytest.mark.asyncio
async def test_async_filter(backend):
    async with async_atomic():
        await AsyncAuthor.async_create(name="Alice", email="alice@example.com", age=30)
        await AsyncAuthor.async_create(name="Bob", email="bob@example.com", age=25)

    results = await AsyncAuthor.objects.async_filter(age=25).all()
    assert len(results) == 1
    assert results[0].name == "Bob"


@pytest.mark.asyncio
async def test_async_get_raises(backend):
    with pytest.raises(Exception):
        await AsyncAuthor.objects.async_get(pk=9999)


@pytest.mark.asyncio
async def test_async_values(backend):
    async with async_atomic():
        await AsyncAuthor.async_create(name="Vance", email="vance@example.com")
    vals = await AsyncAuthor.objects.async_values("name", "email")
    assert isinstance(vals[0], dict)
    assert vals[0]["name"] == "Vance"
    vlist = await AsyncAuthor.objects.async_values_list("name", "email")
    assert ("Vance", "vance@example.com") in vlist


@pytest.mark.asyncio
async def test_async_count_exists(backend):
    assert await AsyncAuthor.objects.async_count() == 0
    async with async_atomic():
        await AsyncAuthor.async_create(name="CountTest", email="count@example.com")
    assert await AsyncAuthor.objects.async_count() == 1
    assert await AsyncAuthor.objects.async_filter(name="CountTest").async_exists() is True


@pytest.mark.asyncio
async def test_async_transaction_commit(backend):
    async with async_atomic():
        await AsyncItem.async_create(name="txn1")
        await AsyncItem.async_create(name="txn2")
    assert await AsyncItem.objects.async_count() == 2


@pytest.mark.asyncio
async def test_async_transaction_rollback(backend):
    initial = await AsyncItem.objects.async_count()
    try:
        async with async_atomic():
            await AsyncItem.async_create(name="bad")
            raise RuntimeError("rollback me")
    except RuntimeError:
        pass
    assert await AsyncItem.objects.async_count() == initial


@pytest.mark.asyncio
async def test_async_foreign_key(backend):
    async with async_atomic():
        author = await AsyncAuthor.async_create(name="FKAuth", email="fk@example.com")
        post = await AsyncPost.async_create(title="Post1", author=author)
    fetched = await AsyncPost.objects.async_get(pk=post.pk)
    assert fetched.author.pk == author.pk
    assert fetched.author.name == "FKAuth"


def pytest_collection_modifyitems(config, items):
    # Ensure the backend fixture updates itself per param
    pass

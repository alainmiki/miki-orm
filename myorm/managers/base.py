"""Base manager class for query and persistence APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .queryset import QuerySet

from ..models.base import Model


class Manager:
    """Default manager exposing Django-like query methods.

    Each model class gets a Manager instance attached as ``objects``
    by the metaclass.

    Users can define custom managers by subclassing Manager and
    assigning an instance to a class attribute on their model.
    """

    model: type[Model]

    def __init__(self, model: type[Model]) -> None:
        self.model = model

    def all(self) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model)

    def filter(self, *args: Any, **kwargs: Any) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).filter(*args, **kwargs)

    def exclude(self, *args: Any, **kwargs: Any) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).exclude(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Model:
        from .queryset import QuerySet

        return QuerySet(self.model).get(*args, **kwargs)

    def get_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Model, bool]:
        from .queryset import QuerySet

        return QuerySet(self.model).get_or_create(defaults=defaults, **kwargs)

    def get_object_or_404(self, *args: Any, **kwargs: Any) -> Model:
        from .queryset import QuerySet

        try:
            return QuerySet(self.model).get(*args, **kwargs)
        except Exception:
            from ..models.base import ObjectDoesNotExist

            raise ObjectDoesNotExist(
                f"{self.model.__name__} matching query does not exist."
            )

    def create(self, **kwargs: Any) -> Model:
        obj = self.model(**kwargs)
        obj.save()
        return obj

    def first(self) -> Model | None:
        from .queryset import QuerySet

        return QuerySet(self.model).first()

    def last(self) -> Model | None:
        from .queryset import QuerySet

        return QuerySet(self.model).last()

    def count(self) -> int:
        from .queryset import QuerySet

        return QuerySet(self.model).count()

    def exists(self) -> bool:
        from .queryset import QuerySet

        return QuerySet(self.model).exists()

    def update_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Model, bool]:
        from .queryset import QuerySet

        return QuerySet(self.model).update_or_create(defaults=defaults, **kwargs)

    def bulk_create(self, objs: list[Model], batch_size: int = 1000) -> list[Model]:
        for obj in objs:
            obj.save()
        return objs

    def update(self, **values: Any) -> int:
        from .queryset import QuerySet

        return QuerySet(self.model).update(**values)

    def values(self, *fields: str) -> list[dict[str, Any]]:
        from .queryset import QuerySet

        return QuerySet(self.model).values(*fields)

    def values_list(self, *fields: str) -> list[tuple[Any, ...]]:
        from .queryset import QuerySet

        return QuerySet(self.model).values_list(*fields)

    def select_related(self, *related: str) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).select_related(*related)

    def prefetch_related(self, *related: str) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).prefetch_related(*related)


class ManagerDescriptor:
    """Descriptor that returns the Manager instance for a model class.

    This allows ``MyModel.objects`` to return a Manager rather than a
    bound method, while still allowing custom managers to be defined.
    """

    def __get__(self, obj: Any, cls: type[Model] | None = None) -> Manager:
        if cls is None:
            raise AttributeError("Manager must be accessed via a model class.")
        # If the class defined its own manager as a class attribute,
        # return that (supports custom managers).
        for attr_name in dir(cls):
            attr = cls.__dict__.get(attr_name)
            if isinstance(attr, Manager) and attr_name != "_default_manager":
                return attr
        # Otherwise return the default manager stored by the metaclass
        if hasattr(cls, "_default_manager"):
            return cls._default_manager
        raise AttributeError(f"{cls.__name__} has no manager.")

    def __set__(self, obj: Any, value: Any) -> None:
        raise AttributeError("Cannot assign to 'objects' directly.")
from typing import Optional, Type

from patterns.singleton._unique_key_getter import GlobalUniqueKeyGetter
from patterns.singleton._implementation import SingletonImpl, T, UniqueKeyGetter


class Singleton:
    def __init_subclass__(cls, **kwargs):
        _ = _make_singleton(
            cls, unique_key_getter=kwargs.get('unique_key_getter', None)
        )


def singleton(
    cls_: Optional[Type[T]] = None,
    unique_key_getter: Optional[UniqueKeyGetter] = None,
):
    decorator =  SingletonDecorator(unique_key_getter)
    if cls_ is not None:
        return decorator(cls_)
    else:
        return decorator


class SingletonDecorator:
    def __init__(self, unique_key_getter: Optional[UniqueKeyGetter]):
        self.unique_key_getter = unique_key_getter

    def __call__(self, cls: Type[T]):
        return _make_singleton(cls, self.unique_key_getter)


def _make_singleton(cls_: Type[T], unique_key_getter: Optional[UniqueKeyGetter]):
    unique_key_getter = GlobalUniqueKeyGetter() if unique_key_getter is None else unique_key_getter
    impl = SingletonImpl(cls_, unique_key_getter)
    cls_.__init__ = impl.init
    cls_.__new__ = impl.new
    return cls_

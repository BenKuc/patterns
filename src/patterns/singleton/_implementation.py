import abc
from typing import Type, TypeVar, Hashable, Dict


class UniqueKeyGetter(abc.ABC):
    @abc.abstractmethod
    def get(self, *args, **kwargs) -> Hashable:
        ...


T = TypeVar('T')


class InstanceWrapper:
    def __init__(self, instance: T):
        self.instance = instance
        self.initialized = False


class SingletonImpl:

    def __init__(self, cls_: Type[T], unique_key_getter: UniqueKeyGetter):
        self.cls_ = cls_
        self.original_new = cls_.__new__
        self.original_init = cls_.__init__
        self._unique_key_getter = unique_key_getter
        self._instance_map: Dict[Hashable, InstanceWrapper] = {}

    # for equality and tuple, we need to analyze the args and kwargs in new signature
    # -> are there any restrictions?
    def new(self, *args, **kwargs):
        unique_key = self._unique_key_getter.get(*args, **kwargs)
        if unique_key not in self._instance_map:
            instance = self.original_new(*args, **kwargs)
            self._instance_map[unique_key] = InstanceWrapper(instance)
        return self._instance_map[unique_key]

    def init(self_, *args, **kwargs) -> None:
        unique_key = self_._unique_key_getter.get(*args, **kwargs)
        t_wrapper = self_._instance_map[unique_key]
        if not t_wrapper.initialized:
            self_.original_init(*args, **kwargs)

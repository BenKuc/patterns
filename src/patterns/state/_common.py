# Standard Library
import inspect
import sys
from typing import Any, List, Tuple, Type, Union


def get_relevant_members(cls: Type) -> List[Tuple[str, Any]]:
    return [
        (name, member)
        # __dict__ only contains the member declared on this class without bases
        for name, member in cls.__dict__.items()
        if not name.startswith('__')  # ignore magic methods and so on
    ]


def resolve_type(module: str, type_: Union[str, Type]) -> Type:
    if inspect.isclass(type_):
        return type_
    elif isinstance(type_, str):
        return sys.modules[module].__dict__[type_]
    else:
        raise NotImplementedError

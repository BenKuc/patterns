# Standard Library
from dataclasses import dataclass, field
from typing import Any, Callable, List, Type, Union


@dataclass
class Implementation:
    implementation: Union[str, Type, Callable]
    on: Type


@dataclass
class StateMemberBase:
    name: str
    defined_on: Type
    definition: Any
    implementations: List[Implementation] = field(default_factory=list)

    def add_implementation(self, implementation: Implementation):
        self.implementations.append(implementation)

    @property
    def is_implemented(self) -> bool:
        return bool(self.implementations)


def hash_number():
    num = 0
    while True:
        yield num
        num += 1


hash_number_generator = hash_number()


class StateMember(StateMemberBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hash_number = next(hash_number_generator)

    def __hash__(self) -> int:
        return hash((StateMemberBase, self._hash_number))

    def __eq__(self, other: 'StateMember') -> bool:
        return self._hash_number == other._hash_number


class StateAttribute(StateMember):
    pass


class StateMethod(StateMember):
    pass


class StateTransition(StateMember):
    def __init__(self, *args, to: Union[str, Type], **kwargs):
        super().__init__(*args, **kwargs)
        self.to = to

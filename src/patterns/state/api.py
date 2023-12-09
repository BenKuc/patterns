# Standard Library
from types import MappingProxyType
from typing import Callable, Dict, List, Optional, Tuple, Type, Union

# Patterns
from patterns.state._add import AddState
from patterns.state._resolver import (
    ClassRegistryMap,
    MemberRegistryMap,
    StateRegistryResolver,
)
from patterns.state._structs import (
    ClassStateItem,
    MemberStateItem,
    StateMethod,
    StateProperty,
    StateTransition,
)
from patterns.state.exceptions import StateConfigError

__all__ = [
    'StateRegistry',
    'add_state',
]


class StateRegistry:
    """Expose decorators to define and register the state-api."""

    def __init__(self):
        self._is_resolved = False
        self._member_registry: Dict[Tuple[str, str], MemberStateItem] = {}
        self._registry: Dict[Tuple[str, str], ClassStateItem] = {}

    # don't know if this is needed, but if a registry is resolved, one can copy it
    # basically an go on from an unresolved state
    def extend(self) -> 'StateRegistry':
        registry = StateRegistry()
        registry._member_registry = dict(self._member_registry)
        registry._registry = dict(self._registry)
        return registry

    def register(
        self,
        cls: Type = None,
        initial: bool = False,
        abstract: bool = False,
        attributes: List[str] = None,
    ):
        self._check_is_unresolved()

        def decorator(cls: Type):
            self._registry[(cls.__module__, cls.__name__)] = ClassStateItem(
                cls, initial, abstract, attributes=attributes or []
            )
            return cls

        return decorator if cls is None else decorator(cls)

    def method(self, function: Optional[Callable] = None):
        self._check_is_unresolved()

        def decorator(func):
            state_item = self._get_member_state_item(function)
            state_item.methods[func.__name__] = StateMethod(func)
            return func

        return decorator if function is None else decorator(function)

    def property_(self, function: Optional[Callable] = None):
        self._check_is_unresolved()

        def decorator(func):
            state_item = self._get_member_state_item(function)
            state_item.properties[func.__name__] = StateProperty(func)
            return property(func)

        return decorator if function is None else decorator(function)

    def transition(
        self,
        /,
        *,
        to: Union[str, Type['StateRegistry']],
    ):
        self._check_is_unresolved()

        def decorator(function: Callable) -> Callable:
            state_item = self._get_member_state_item(function)
            state_item.transitions[function.__name__] = StateTransition(
                function, transitions_to=to
            )
            return function

        return decorator

    def _get_member_state_item(self, function: Callable) -> MemberStateItem:
        registry_key = self._get_registry_key(function)
        if registry_key not in self._member_registry:
            self._member_registry[registry_key] = MemberStateItem()
        return self._member_registry[registry_key]

    def _get_registry_key(self, function: Callable) -> Tuple[str, str]:
        # __qualname__ == class.function
        return function.__module__, function.__qualname__.partition('.')[0]

    def _check_is_unresolved(self):
        if self._is_resolved:
            raise StateConfigError(
                'StateRegistry object was resolved and cannot be used anymore to '
                'register states or add them. This is a safety mechanism to achieve '
                'consistency with other functionality this package provides.'
            )

    @property
    def resolved(self) -> bool:
        return self._is_resolved

    def resolve(self) -> (ClassRegistryMap, MemberRegistryMap):
        self._is_resolved = True
        return MappingProxyType(self._registry), MappingProxyType(self._member_registry)


# Standard Library
import os

CREATE_OR_UPDATE_PYI_FILES_RAW = os.environ.get(
    'PATTERNS_STATE_CREATE_OR_UPDATE_PYI_FILES', 'false'
)
valid_map = {
    'true': True,
    'false': False,
}
if CREATE_OR_UPDATE_PYI_FILES_RAW.lower() not in valid_map:
    # TODO(BK): more verbose error message
    raise RuntimeError('Env-var not in expected format.')
CREATE_OR_UPDATE_PYI_FILES = valid_map[CREATE_OR_UPDATE_PYI_FILES_RAW.lower()]
# Patterns
from patterns.state._stubs import generate_stubs


def add_state(state: StateRegistry):
    def decorator(cls: Type):
        if state.resolved:
            raise StateConfigError('Given StateRegistry is already resolved.')

        resolver = StateRegistryResolver()
        class_registry_map, member_registry_map = state.resolve()
        resolved_state_definition = resolver.resolve(
            class_registry_map, member_registry_map
        )
        add_state_instance = AddState(resolved_state_definition)
        add_state_instance.add_state_to(cls)
        # TODO(BK): experimental to overcome the loading issue stuff...
        if CREATE_OR_UPDATE_PYI_FILES:
            breakpoint()
            generate_stubs(path=cls.__file__, overwrite=True)
        return cls

    return decorator

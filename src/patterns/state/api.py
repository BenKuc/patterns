# Standard Library
from typing import Type, Union

# Patterns
from patterns.state._collectors import (
    TRANSITION_MARKER_KEY,
    StateClsType,
    StateDefinition,
)
from patterns.state._exceptions import StateConfigError, StateError

__all__ = [
    'StateConfigError',
    'StateDefinition',
    'StateError',
    'StateClsType',
    'state_transition',
]


def state_transition(to: Union[str, Type]):
    def decorator(func):
        setattr(func, TRANSITION_MARKER_KEY, to)
        return func  # leave untouched, just mark it temporarily

    return decorator

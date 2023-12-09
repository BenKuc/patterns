# Standard Library
from typing import Type

# Patterns
from patterns.state._code_gen import (
    composed_wrapper_generator_factory,
    create_wrapped_state_init,
)
from patterns.state._structs import StateDefinition
from patterns.state.exceptions import StateConfigError


class AddState:
    """Adds the api from a resolved state-registry to the target class."""

    _cls_to_state = {}

    def __init__(self, state_definition: StateDefinition):
        self.state_definition = state_definition

    def add_state_to(self, cls: Type):
        if cls in AddState._cls_to_state:
            raise StateConfigError(f'class {cls} was already added a state.')

        def decorator(cls: Type):
            self._add_state_property(cls)
            self._add_state_members(cls)
            AddState._cls_to_state[cls] = self.state_definition
            return cls

        return decorator if cls is None else decorator(cls)

    def _add_state_property(self, cls: Type):
        def state(self):
            return self._state

        cls.state = property(state)

        init_wrapper = create_wrapped_state_init(
            cls, initial_state=self.state_definition.initial
        )
        cls.__init__ = init_wrapper

    def _add_state_members(self, cls: Type):
        for concrete_state_item in self.state_definition.concretes:
            for state_member in concrete_state_item.members:
                generator = composed_wrapper_generator_factory(member=state_member)
                wrapper = generator.create_wrapper()
                wrapper = state_member.modify_wrapper(wrapper)
                setattr(cls, state_member.name, wrapper)

    @classmethod
    def cls_to_state(cls):
        return cls._cls_to_state

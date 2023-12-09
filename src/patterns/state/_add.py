# Standard Library
from typing import Type

# Patterns
from patterns.state import settings
from patterns.state._code_gen import (
    composed_wrapper_generator_factory,
    create_wrapped_state_init,
)
from patterns.state._structs import StateDefinition
from patterns.state.exceptions import StateConfigError

unset = object()


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
        members_added_by_state = set()
        for concrete_state_item in self.state_definition.concretes:
            state_cls_member_set = set()
            for state_member in concrete_state_item.members:
                generator = composed_wrapper_generator_factory(member=state_member)
                member_name = state_member.name

                original_member = getattr(cls, member_name, unset)
                # we don't consider all cases of members with the same name but that are
                # actually different on different classes; for now we just assume they
                # are the same and overwrite them a few times if shared among a few
                # state-classes -> maybe we miss a few cases with this approach, but as
                # long as no such case shows up, we spare the effort to track the
                # member's class it originates from
                if original_member is unset or member_name in members_added_by_state:
                    wrapper = generator.create_wrapper()
                    wrapper = state_member.modify_wrapper(wrapper)
                    setattr(cls, member_name, wrapper)
                    state_cls_member_set.add(member_name)
                else:
                    raise StateConfigError(
                        f"cannot add member '{member_name}' to class {cls} as it "
                        f'already has a member with this name'
                    )

            members_added_by_state.update(state_cls_member_set)
            setattr(
                concrete_state_item.cls,
                settings.STATE_CLS_MEMBER_SET_KEY,
                state_cls_member_set,
            )

    @classmethod
    def cls_to_state(cls):
        return cls._cls_to_state

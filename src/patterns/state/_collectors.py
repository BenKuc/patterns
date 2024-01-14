# Standard Library
from collections import defaultdict
import enum
import inspect
import itertools
import logging
from types import MappingProxyType
from typing import Any, Callable, Dict, Optional, Set, Type

# Patterns
from patterns.state._common import get_relevant_members, resolve_type
from patterns.state._exceptions import StateConfigError, StateError
from patterns.state._structs import (
    Implementation,
    StateAttribute,
    StateMember,
    StateMethod,
    StateTransition,
)

TRANSITION_MARKER_KEY = '__patterns_state_transition__'
METHOD_MARKER_KEY = '__patterns_state_method__'
DEFAULT_IMPLEMENTATION_CLS_KEY = 'default_state_cls'


logger = logging.getLogger(__file__)


class StateClsType(str, enum.Enum):
    definition = 'definition'
    state = 'state'
    holder = 'holder'


# for state-implementation classes not defining an init
def state_empty_init(*args, **kwargs):
    pass


def state_definition_init(*args, **kwargs):
    raise StateConfigError('State definition should never be initialized.')


def state_cls_init(*args, **kwargs):
    raise StateConfigError(
        'State class and according definition were never used in a class that holds '
        'them.'
    )


class StateMemberDescriptor:
    def __init__(
        self,
        state_attr_name: str,
        attr_name: str,
        implementation_map: Dict[Type, Set[str]],
    ):
        self.state_attr_name = state_attr_name
        self.attr_name = attr_name
        self.implementations = implementation_map

    def __get__(self, instance: Any, owner: Type):
        state_instance = getattr(instance, self.state_attr_name)
        implemented_members = self.implementations[state_instance.__class__]
        if self.attr_name not in implemented_members:
            raise StateError(
                f'Member {self.attr_name} is not available on class '
                f'{owner.__qualname__} in state {state_instance.__class__.__qualname__}.'
            )
        return getattr(state_instance, self.attr_name)


class StateTransitionWrapper:
    def __init__(self, instance: Any, state_attr_name: str, transition: Callable):
        self.instance = instance
        self.state_attr_name = state_attr_name
        self.transition = transition

    def __call__(self, *args, **kwargs):
        new_state = self.transition(*args, **kwargs)
        setattr(self.instance, self.state_attr_name, new_state)


class StateTransitionDescriptor(StateMemberDescriptor):
    def __get__(self, instance: Any, owner: Type):
        return StateTransitionWrapper(
            instance,
            self.state_attr_name,
            transition=super().__get__(instance, owner),
        )


class StateDefinition:
    """Main class for the api. Clients inherit from it to make use of state pattern."""

    def __init_subclass__(cls, **kwargs):
        _global_state_collector.collect(cls, cls_kwargs=kwargs)


class StateCollector:
    def __init__(self, definition: Type):
        self.definition = definition
        self.state_members = MappingProxyType(
            {
                member.name: member
                for member in self.collect_state_members_from_definition()
            }
        )
        self._resolved = False

        # a definition should never be initialized
        definition.__init__ = state_definition_init

        for base in definition.__bases__:
            if issubclass(base, StateDefinition) and base is not StateDefinition:
                raise StateConfigError(
                    f'state-definition class {definition.__qualname__} inherits from '
                    f'another state-definition or implementation class '
                    f'{base.__qualname__}. This might lead to unexpected behaviour and'
                    f' is thereby not allowed.'
                )

        self.implementation_cls_init_map: Dict[Type, Callable] = {}
        self.used_by_holder = False

    def resolve(self):
        self._resolved = True

    def collect_state_members_from_definition(self) -> Set[StateMember]:
        state_members = set()

        for name, annotation in self.definition.__annotations__.items():
            state_members.add(
                StateAttribute(
                    name,
                    defined_on=self.definition,
                    definition=annotation,
                )
            )

        unhandled_members = []
        for name, member in get_relevant_members(self.definition):
            if inspect.isfunction(member):
                init_kwargs = {
                    'name': name,
                    'defined_on': self.definition,
                    'definition': member,
                }
                transition_to = getattr(member, TRANSITION_MARKER_KEY, None)
                if transition_to is not None:
                    state_member_cls = StateTransition
                    delattr(member, TRANSITION_MARKER_KEY)
                    init_kwargs['to'] = transition_to
                else:
                    state_member_cls = StateMethod

                state_members.add(state_member_cls(**init_kwargs))
            else:
                unhandled_members.append(member)

        if unhandled_members:
            raise StateConfigError(
                f'State definition class {self.definition.__qualname__} has members'
                f' that are not transition-methods, nor regular methods: '
                f'{unhandled_members}.'
            )

        return state_members

    def collect_implementations(self, implementation_cls: Type):
        if self._resolved:
            raise StateConfigError(
                'Cannot collect implementations for a definition that was already '
                'resolved, i.e. used in a state-holder-class.'
            )

        collected_at_least_one_implementation = False
        for name, member in [
            *[
                (param.name, param.annotation)
                for param in inspect.signature(
                    implementation_cls.__init__
                ).parameters.values()
            ],
            *[
                (name, annotation)
                for name, annotation in implementation_cls.__annotations__.items()
            ],
            *[
                (name, member)
                for name, member in get_relevant_members(implementation_cls)
            ],
        ]:
            if name not in self.state_members:
                continue

            collected_at_least_one_implementation = True
            state_member = self.state_members[name]
            state_member.add_implementation(
                Implementation(on=implementation_cls, implementation=member)
            )

        if not collected_at_least_one_implementation:
            raise StateConfigError(
                f'State class {implementation_cls.__qualname__} must implement at least'
                f' one state-member.'
            )

        original_init = implementation_cls.__init__
        self.implementation_cls_init_map[implementation_cls] = (
            original_init
            if original_init is not state_definition_init
            else state_empty_init
        )
        implementation_cls.__init__ = state_cls_init

    @property
    def member_names(self):
        return set(member.name for member in self.members)

    @property
    def members(self):
        return set(self.state_members.values())


class GlobalCollector:
    def __init__(self):
        self.state_collectors: Dict[Type, StateCollector] = {}

    def collect(self, cls: Type, cls_kwargs: Dict[str, Any]):
        try:
            state_cls_type = StateClsType(cls_kwargs['state_cls_type'])
        except (KeyError, ValueError):
            raise StateConfigError(
                f"Subclass {cls.__qualname__} must set 'state_cls_type' in class "
                f"definition, like\n "
                f"class {cls.__name__}"
                f"({', '.join([base.__name__ for base in cls.__bases__])},"
                f" state_cls_type=...)"
                f"\nwhere ... is one of {list(StateClsType)}."
            )

        if state_cls_type is StateClsType.definition:
            self.validate_definition_bases(definition=cls)
            self.state_collectors[cls] = StateCollector(definition=cls)
            return
        elif state_cls_type is StateClsType.state:
            definition = self.find_definition_for_implementation(state_cls=cls)
            state_collector = self.state_collectors[definition]
            state_collector.collect_implementations(implementation_cls=cls)
        elif state_cls_type is StateClsType.holder:
            resolver = StateHolderResolver(
                cls,
                MappingProxyType(cls_kwargs),
                MappingProxyType(self.state_collectors),
            )
            resolver.resolve()
        else:
            raise NotImplementedError(
                f'Unhandled StateClsType {state_cls_type}. This is a bug.'
            )

    def find_definition_for_implementation(self, state_cls: Type) -> Type:
        definition_bases = set(
            base for base in reversed(state_cls.mro()) if base in self.state_collectors
        )
        if len(definition_bases) > 1:
            raise StateConfigError(
                f'State-implementation classes should inherit from exactly one '
                f'definition. Class {state_cls.__qualname__} ininherits from more than'
                f' one: {definition_bases}'
            )
        elif len(definition_bases) == 0:
            raise StateConfigError(
                'State-implementation classes should inherit from exactly one '
                f'definition. Could not find any for class {state_cls.__qualname__}.'
            )
        else:
            return definition_bases.pop()

    def validate_definition_bases(self, definition: Type):
        wrong_bases = [
            base
            for base in definition.__bases__
            if issubclass(base, StateDefinition)
            and base not in self.state_collectors
            and base is not StateDefinition
        ]
        if wrong_bases:
            raise StateConfigError(
                'A definition is only allowed to inherit from other StateDefinition '
                f'subclasses if it is a definition itself, but cls '
                f'{definition.__qualname__} inherits from {wrong_bases} which is'
                f'/are not.'
            )


_global_state_collector = GlobalCollector()


class StateHolderResolver:
    def __init__(
        self,
        holder_cls: Type,
        holder_cls_kwargs: MappingProxyType[str, Any],
        state_collectors: MappingProxyType[Type, 'StateCollector'],
    ):
        self.holder_cls = holder_cls
        self.holder_cls_kwargs = holder_cls_kwargs
        self.state_collectors = state_collectors

    def resolve(self):
        self.validate_no_definition_overlap()

        for name, definition in self.get_state_holder_annotations():
            StateHolderDefinitionResolver(
                holder_cls=self.holder_cls,
                holder_cls_kwargs=self.holder_cls_kwargs,
                state_attribute_name=name,
                state_collector=self.state_collectors[definition],
            ).resolve()

    def validate_no_definition_overlap(self):
        common_member_messages = []
        state_holder_annotations = self.get_state_holder_annotations()
        for (name1, definition1), (name2, definition2) in itertools.product(
            state_holder_annotations, state_holder_annotations
        ):
            if definition1 is not definition2:
                members1 = self.state_collectors[definition1].member_names
                members2 = self.state_collectors[definition2].member_names
                common = members1.intersection(members2)
                if common:
                    common_member_messages.append(
                        f'Definition of state-attributes {name1} and {name2} with '
                        f'types {definition1.__qualname__} and '
                        f'{definition2.__qualname__} have common member names {common}.'
                    )

        if common_member_messages:
            msg = '\n'.join(common_member_messages)
            raise StateConfigError(
                f'State attribute definitions for class {self.holder_cls.__qualname__} '
                f'have common member names, which is not permittee: {msg}'
            )

    def get_state_holder_annotations(self):
        state_holder_annotations = []
        invalid_annotations = []

        all_annotations = {
            **{
                param.name: param.annotation
                for param in inspect.signature(
                    self.holder_cls.__init__
                ).parameters.values()
            },
            **self.holder_cls.__annotations__,
        }

        for name, type_anno in all_annotations.items():
            type_ = resolve_type(module=self.holder_cls.__module__, type_=type_anno)
            if not issubclass(type_, StateDefinition):
                continue
            elif type_ not in self.state_collectors:
                invalid_annotations.append((name, type_))
            else:
                state_holder_annotations.append((name, type_))

        if not state_holder_annotations:
            raise StateConfigError(
                'Class that holds state must have a state-attribute indicated by an '
                'annotation to a state-definition.'
            )
        elif invalid_annotations:
            raise StateConfigError(
                f'State attribute annotation can only be a state-definition, '
                f'but got: {invalid_annotations}'
            )

        return state_holder_annotations


class StateHolderDefinitionResolver:
    def __init__(
        self,
        holder_cls: Type,
        holder_cls_kwargs: MappingProxyType[str, Any],
        state_attribute_name: str,
        state_collector: StateCollector,
    ):
        self.holder_cls = holder_cls
        self.holder_cls_kwargs = holder_cls_kwargs
        self.state_attribute_name = state_attribute_name
        self.state_collector = state_collector
        self.definition = state_collector.definition

    def resolve(self):
        self.validate_inherits_from_state_attribute_definition()
        self.validate_all_members_implemented()
        self.validate_transitions_reach_all_states()
        self.set_original_inits()
        self.set_state_member_descriptors()
        self.state_collector.resolve()

    def validate_inherits_from_state_attribute_definition(self):
        if self.definition not in self.holder_cls.__bases__:
            raise StateConfigError(
                f'State holding class {self.holder_cls.__qualname__} must inherit from '
                f'state-definition class {self.definition.__qualname__} as it will'
                f' inherit all of its members via state-attribute '
                f'{self.state_attribute_name}.'
            )

    def validate_all_members_implemented(self):
        definition_members = self.state_collector.members
        unimplemented_members = set(
            member for member in definition_members if not member.implementations
        )
        if unimplemented_members:
            raise StateConfigError(
                f'The following members are not implemented in any of '
                f'{self.definition.__qualname__} bases: {unimplemented_members}. Either'
                f' delete or implement them.'
            )

    def get_state_implementation_classes(self):
        definition_members = self.state_collector.members
        return set(
            implementation.on
            for member in definition_members
            for implementation in member.implementations
        )

    def validate_default_implementation_cls(self) -> Optional[Type]:
        state_implementation_classes = self.get_state_implementation_classes()

        try:
            default_implementation_cls = self.holder_cls_kwargs[
                DEFAULT_IMPLEMENTATION_CLS_KEY
            ]
        except KeyError:
            raise StateConfigError(
                f'State holder class {self.holder_cls.__qualname__} needs to set '
                f'{DEFAULT_IMPLEMENTATION_CLS_KEY} argument in class definition like\n'
                f"class {self.holder_cls.__name__}(<bases>, state_cls_type='holder', "
                f'{DEFAULT_IMPLEMENTATION_CLS_KEY}=<default_state_cls>). Where '
                f'default_state_cls is either None, if any state is possible at init'
                f'time of an instance of {self.holder_cls.__qualname__} or one of the '
                f'following: {state_implementation_classes}.'
            )

        if default_implementation_cls not in {*state_implementation_classes, None}:
            raise StateConfigError(
                f'{DEFAULT_IMPLEMENTATION_CLS_KEY} of state holder class '
                f'{self.holder_cls.__qualname__} must either be None or one of the '
                f'following: {state_implementation_classes}'
            )

        return default_implementation_cls

    def validate_transitions_reach_all_states(self):
        state_implementation_classes = self.get_state_implementation_classes()
        reachable_states = set()
        # get the default as a start or arbitrary one if the default is not given
        default_implementation_cls = self.validate_default_implementation_cls()
        states_to_check = {
            default_implementation_cls or state_implementation_classes.pop()
        }

        state_transition_map = defaultdict(set)
        for member in self.state_collector.members:
            if not isinstance(member, StateTransition):
                continue
            for impl in member.implementations:
                state_transition_map[impl.on].add(member)

        while states_to_check:
            implementation_cls = states_to_check.pop()
            reachable_states.add(implementation_cls)
            for transition in state_transition_map[implementation_cls]:
                module = implementation_cls.__module__
                to = resolve_type(module, type_=transition.to)
                if to not in reachable_states:
                    states_to_check.add(to)

        unreachable_states = state_implementation_classes.difference(reachable_states)
        if unreachable_states:
            msg_add_on = (
                ''
                if default_implementation_cls is None
                else f'from {default_implementation_cls.__qualname__}'
            )
            raise StateConfigError(
                f'Cannot reach all state-classes via transitions {msg_add_on}.'
                f'Unreachable states: {unreachable_states}.'
            )

    def set_original_inits(self):
        impl_cls_init_map = self.state_collector.implementation_cls_init_map
        for impl_cls in self.get_state_implementation_classes():
            original_init = impl_cls_init_map[impl_cls]
            impl_cls.__init__ = original_init

    def set_state_member_descriptors(self):
        state_members = self.state_collector.members
        implementation_map = defaultdict(set)
        for member in state_members:
            for impl in member.implementations:
                implementation_map[impl.on].add(member.name)

        implementation_map = dict(implementation_map)

        for member in state_members:
            descriptor_cls = (
                StateTransitionDescriptor
                if isinstance(member, StateTransition)
                else StateMemberDescriptor
            )
            descriptor = descriptor_cls(
                self.state_attribute_name,
                attr_name=member.name,
                implementation_map=implementation_map,
            )
            setattr(self.holder_cls, member.name, descriptor)

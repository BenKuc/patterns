# Standard Library
from collections import deque
import inspect
from types import MappingProxyType
from typing import List, Tuple, Type

# Patterns
from patterns.state._code_gen import resolve_type
from patterns.state._structs import (
    ClassStateItem,
    InternalItemState,
    MemberStateItem,
    StateAttribute,
    StateDefinition,
    StateItem,
    StateTransition,
)
from patterns.state.exceptions import StateConfigError

ClassRegistryMap = (MappingProxyType[Tuple[str, str], ClassStateItem],)
MemberRegistryMap = (MappingProxyType[Tuple[str, str], MemberStateItem],)


class StateRegistryResolver:
    """Resolve and validate the collected definitions of a state registry."""

    def resolve(
        self,
        class_registry_map: ClassRegistryMap,
        member_registry_map: MemberRegistryMap,
    ) -> StateDefinition:
        matched_state_items = self.match_member_and_class_states(
            class_registry_map, member_registry_map
        )
        resolved_state_items = self.resolve_item_inheritance(matched_state_items)
        self.validate_state_definitions(resolved_state_items)
        initial = self.validate_initial(resolved_state_items)

        concretes = [
            state_item for state_item in resolved_state_items if not state_item.abstract
        ]
        # make sure initial state comes first
        concretes.remove(initial)
        concretes.insert(0, initial)
        state_definition = StateDefinition(
            initial=initial,
            concretes=tuple(concretes),
        )
        self.validate_state_transition_map(state_definition)
        return state_definition

    def match_member_and_class_states(
        self,
        class_registry_map: ClassRegistryMap,
        member_registry_map: MemberRegistryMap,
    ) -> List[StateItem]:
        class_registry_keys = set(class_registry_map.keys())
        member_registry_keys = set(member_registry_map.keys())

        matched_state_items = []
        common_keys = set(class_registry_keys).intersection(member_registry_keys)
        for registry_key in common_keys:
            class_state_item = class_registry_map[registry_key]
            member_state_item = member_registry_map[registry_key]
            matched_state_items.append(
                StateItem(
                    cls=class_state_item.cls,
                    initial=class_state_item.initial,
                    abstract=class_state_item.abstract,
                    attributes=self.get_attributes(class_state_item),
                    properties=MappingProxyType(member_state_item.properties),
                    methods=MappingProxyType(member_state_item.methods),
                    transitions=self.get_transitions(
                        class_state_item.cls, member_state_item
                    ),
                    internal_state=InternalItemState.matched,
                )
            )

        only_class_registry_keys = class_registry_keys.difference(member_registry_keys)
        for registry_key in only_class_registry_keys:
            class_state_item = class_registry_map[registry_key]
            matched_state_items.append(
                StateItem(
                    cls=class_state_item.cls,
                    initial=class_state_item.initial,
                    abstract=class_state_item.abstract,
                    attributes=self.get_attributes(class_state_item),
                    properties=MappingProxyType({}),
                    methods=MappingProxyType({}),
                    transitions=MappingProxyType({}),
                    internal_state=InternalItemState.matched,
                )
            )

        only_member_registry_keys = member_registry_keys.difference(class_registry_keys)
        for registry_key in only_member_registry_keys:
            member_state_item = member_registry_map[registry_key]
            module_name, cls_name = registry_key
            cls = resolve_type(module_name, cls_name)
            matched_state_items.append(
                StateItem(
                    cls=cls,
                    initial=False,
                    abstract=True,
                    attributes=MappingProxyType({}),
                    properties=MappingProxyType(member_state_item.properties),
                    methods=MappingProxyType(member_state_item.methods),
                    transitions=self.get_transitions(cls, member_state_item),
                    internal_state=InternalItemState.matched,
                )
            )

        return matched_state_items

    def get_attributes(
        self, class_state_item: ClassStateItem
    ) -> MappingProxyType[str, StateAttribute]:
        ret_dict = {}
        cls = class_state_item.cls
        for attribute in class_state_item.attributes:
            if attribute in (annotations := cls.__annotations__):
                type_ = annotations[attribute]
            elif (
                attribute
                in (signature := inspect.signature(obj=cls.__init__).parameters)
                and (type_ := signature[attribute].annotation)
                is not inspect.Signature.empty
            ):
                type_ = type_
            else:
                raise StateConfigError(
                    f'State attribute {attribute} must either be annotated on the class'
                    f" or the class's __init__."
                )
            resolved_type = (
                resolve_type(module=cls.__module__, name=type_)
                if isinstance(type_, str)
                else type_
            )
            ret_dict[attribute] = StateAttribute(name=attribute, type_=resolved_type)

        return MappingProxyType(ret_dict)

    def get_transitions(
        self, cls: Type, member_state_item: MemberStateItem
    ) -> MappingProxyType[str, StateTransition]:
        for name, state_transition in member_state_item.transitions.items():
            ret_anno = inspect.signature(state_transition.function).return_annotation
            if (
                ret_anno is not inspect.Signature.empty
                and ret_anno is not state_transition.transitions_to
            ):
                raise StateConfigError(
                    f'State-transition {state_transition.function.__qualname__} does '
                    f"not define same as return-annotation and for 'to' parameter."
                )
            if isinstance(state_transition.transitions_to, str):
                resolved_transitions_to = resolve_type(
                    module=cls.__module__, name=state_transition.transitions_to
                )
                member_state_item.transitions[name] = StateTransition(
                    state_transition.function,
                    transitions_to=resolved_transitions_to,
                )

        return MappingProxyType(member_state_item.transitions)

    def resolve_item_inheritance(
        self, matched_state_items: List[StateItem]
    ) -> List[StateItem]:
        state_item_by_cls = {
            state_item.cls: state_item for state_item in matched_state_items
        }
        resolved_classes = set()
        for state_item in matched_state_items:
            all_bases = state_item.cls.mro()
            all_bases.reverse()
            for base in all_bases:
                if base not in state_item_by_cls or base in resolved_classes:
                    continue
                state_item_for_base = state_item_by_cls[base]
                state_item = state_item.inherit_from_state(other=state_item_for_base)
                state_item = state_item.with_new_internal_state(
                    InternalItemState.resolved
                )
                resolved_classes.add(state_item.cls)
                state_item_by_cls[state_item.cls] = state_item

        return list(state_item_by_cls.values())

    def validate_state_definitions(self, resolved_state_items: List[StateItem]):
        for state_item in resolved_state_items:
            if state_item.abstract and not state_item.members:
                raise StateConfigError(
                    f'Abstract state class {state_item.cls} needs to define members.'
                    f' Otherwise, do not register.'
                )

    def validate_initial(self, state_items: List[StateItem]) -> StateItem:
        initials = [state for state in state_items if state.initial]
        if len(initials) == 0:
            raise StateConfigError(
                'There must be exactly one initial state, but none was declared.'
            )
        elif len(initials) > 1:
            raise StateConfigError(
                f'There must be exactly one initial state, but multiple were declared: {initials}.'
            )

        initial = initials[0]
        if initial.abstract:
            raise StateConfigError(
                f'Declared initial state must not be abstract: {initial}'
            )

        initial_init = initial.cls.__init__
        # object.__init__ is a wrapper that works differently (has *args, **kwargs)
        if (
            initial_init is not object.__init__
            and len(inspect.signature(initial_init).parameters) > 1
        ):
            breakpoint()
            raise StateConfigError(
                f'__init__ of initial state {initial.cls} cannot have additional '
                f"arguments apart from 'self'."
            )

        return initial

    def validate_state_transition_map(self, state_definition: StateDefinition):
        state_items_by_cls = {state.cls: state for state in state_definition.concretes}
        queue = deque()
        queue.append(state_definition.initial)
        reachable_state_classes = set()
        while queue:
            state_item = queue.popleft()
            reachable_state_classes.add(state_item.cls)
            for state_transition in state_item.transitions.values():
                transition_state_cls = state_transition.transitions_to
                state = state_items_by_cls[transition_state_cls]
                if transition_state_cls not in reachable_state_classes:
                    queue.append(state)

        unreachable_states = set(state_items_by_cls).difference(reachable_state_classes)
        if unreachable_states:
            raise StateConfigError(
                f'There are states in the definition that cannot be reached by '
                f'transitions: {[st.cls for st in unreachable_states]}'
            )

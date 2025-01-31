import inspect
from typing import Any, Callable, Dict, Hashable, Tuple

from patterns.singleton._implementation import UniqueKeyGetter


class GlobalUniqueKeyGetter(UniqueKeyGetter):
    _sentinel = object()

    def get(self, *args, **kwargs) -> Hashable:
        return self._sentinel


class HashTupleSignatureUniqueKeyGetter(UniqueKeyGetter):
    def __init__(
        self,
        init_method: Callable,
        hash_func_map: Dict[str, Callable[[Any], Hashable]] = None,
    ):
        self.hash_func_map = hash_func_map or {}

        # do not consider first param (cls or self) and variadic args or kwargs as they
        # will be filtered out by algorithm below
        params = list(inspect.signature(init_method).parameters.values())[1:]
        self.params = [
            param
            for param in params
            if (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]


    def get(self, *args, **kwargs) -> Tuple[Hashable, ...]:
        """
        Get a tuple of hashables considering the whole signature of the init-method.

        This assumes that the values are hashable or an appropriate function to
        calculate a hashable out of them is provided via hash_func_map.

        The below implementation uses the fact that as soon as a parameter is given
        as a keyword argument, all following can only be keyword arguments too.
        """
        args_result = []
        kwargs_result = []
        rest_params = iter(self.params)
        rest_args = iter(args)
        rest_kwargs = dict(kwargs)

        for param, arg_val in zip(rest_params, rest_args):  # ordered by smallest index
            name = param.name
            hash_func = self.hash_func_map.get(name)
            if name not in kwargs:
                val = arg_val if hash_func is None else hash_func(arg_val)
                args_result.append(val)
            else:
                kwarg_val = rest_kwargs.pop(name)
                val = kwarg_val if hash_func is None else hash_func(kwarg_val)
                kwargs_result.append(val)
                break

        for param in rest_params:
            name = param.name
            hash_func = self.hash_func_map.get(name)
            kwarg_val = rest_kwargs.pop(name)
            val = kwarg_val if hash_func is None else hash_func(kwarg_val)
            kwargs_result.append(val)

        # assume values are hashable, and make robust against naming
        var_pos_args_result = list(rest_args)
        var_kwargs_result = [rest_kwargs[key] for key in sorted(rest_kwargs)]

        return tuple([*args_result, *kwargs_result, *var_pos_args_result, *var_kwargs_result])
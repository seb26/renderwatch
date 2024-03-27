from .renderjob import RenderJob
from .exceptions import UserInvalidConfig

import logging
from functools import partial
from typing import Any, Callable

logger = logging.getLogger(__name__)

class Step(object):
    methods = {}
    required_params = {}
    renderwatch = None

    def __init__(
        self,
        action_keyword: str = None,
        index: int = None,
        step_type: str = None,
        renderwatch = None,
        trigger: str = None,
    ):
        self.action_keyword = action_keyword
        self.index = index
        self.renderwatch = renderwatch
        self.step_type = step_type
        self.trigger = trigger
    
    @classmethod
    def action(self, action_keyword: str, *args, params: list = []):
        def decorator(func):
            instance = partial(
                func,
                self,
            )
            self._register_method(action_keyword, instance, params)
            return instance
        return decorator

    @classmethod
    def _register_method(
        self,
        action_keyword: str,
        method: Callable[[str], Any],
        params: list,
    ):
        self.methods[action_keyword] = method
        self.required_params[action_keyword] = params

    @classmethod
    def run(
        self,
        func,
        *args,
        callback_pre: Callable,
        callback_post: Callable,
        **kwargs,
    ):
        callback_pre()
        result = func(
            self,
            *args,
            **kwargs,
        )
        callback_post()
        return result

    def get_method_from_keyword(self, action_keyword: str):
        """Sets the Step's `action` keyword and returns the method connected to it"""
        if action_keyword in self.methods:
            self.action_keyword = action_keyword
            return self.methods[action_keyword]
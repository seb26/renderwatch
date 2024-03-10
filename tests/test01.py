import logging
from functools import partial, wraps
from pprint import pprint
from types import MethodType
from typing import Any, Callable

from events import Events
from enum import Enum

logger = logging.getLogger(__name__)

class BaseEventGroup(Events):
    group_name = None
    events = ()

    def __init__(self):
        super(BaseEventGroup, self).__init__()
        # Name should evaluate to: renderwatch.event.group_name
        self.logger = logging.getLogger(__name__ + '.' + self.group_name)
        for event_name in self.__events__:
            # Get a handler per this event name
            handler = getattr(self, event_name)
            # Attach some log wrappers
            handler += partial(self.log, event_name)

    def log(self, *args, **kwargs):
        print('args', args)
        print('kwargs', kwargs)

class EventGroup(BaseEventGroup):
    group_name = 'my_group_name'
    __events__ = (
        'event1',
        'event2'
    )

class Step(object):
    methods = {}
    def __init__(self, keyword: str = None, trigger: str = None, step_type: str = None, index: int = None):
        self.index = index
        self.keyword = keyword
        self.trigger = trigger
        self.step_type = step_type
    
    @classmethod
    def action(self, action_keyword: str):
        def decorator(func):
            self._register_method(action_keyword, func)
            return partial(
                func,
                self
            )
        return decorator
    
    """ tried but it had no influence?
    def __getattribute__(self, attr):
        instance = object.__getattribute__(self, attr)
        if isinstance(instance, partial):    
            return MethodType(instance, self, type(self))
        else:
            return instance
    """

    @classmethod
    def _register_method(self, action_keyword: str, method: Callable):
        self.methods[action_keyword] = method

    @classmethod
    def run(self, func, *args, **kwargs):
        print('run func, args, kwargs', func, args, kwargs)
        print('func-renderwatch', func.keywords['renderwatch'])
        return func(
            *args,
            renderwatch = func.keywords['renderwatch'],
            **kwargs,
        )
    
    def get_method_from_keyword(self, keyword: str):
        """Sets the Step's keyword and returns the method represented by it"""
        if keyword in self.methods:
            self.keyword = keyword
            return self.methods[keyword]

class Telegram(Step):
    def __init__(self, token: str = 'DEFAULT TOKEN'):
        super(Telegram, self).__init__()
        self.token = token
        self.attrib_only_locally = 'line 82'

    @Step.action('keyword_send_telegram_notification')
    def send_telegram_notification(
        context,
        chat_id: str = None,
        **kwargs
    ):
        print('\n  send_telegram_notification():')
        print('  context:', context.__dict__)
        """print('  instance', instance)
        if hasattr(instance, '__dict__'):
            print('instance dict', instance.__dict__)"""
        print('  chat-id', chat_id)
        print('  KWARGS', kwargs)

class Steps(Enum):
    telegram = Telegram

class Renderwatch(object):
    def __init__(self):
        self.renderwatch_attrib = 'x'
        self.event_manager = EventGroup()
        self.config = { 'steps': {
            'telegram': {
                'token': 'SECRET_TOKEN_86',
            }
        }}
        self.setup()

    def format_text(self, text):
        return 'xxxx' + text + 'xxxx'

    def setup(self):
        user_keyword = 'keyword_send_telegram_notification'
        user_triggers = [ 'event1', 'event2', ]
        user_step_type = 'telegram'

        user_config = self.config['steps'][user_step_type]

        action_steps = []
        for trigger in user_triggers:
            step_class = Steps[user_step_type].value
            step_instance = step_class(
                **user_config,
            )
            step_instance.keyword = user_keyword
            step_instance.trigger = trigger
            step_instance.step_type = user_step_type
            step_instance.index = 2
            # Add our renderwatch context
            step_instance.renderwatch = self
            step_instance.abc = 'XYZ'

            step_method = step_instance.get_method_from_keyword(user_keyword)

            print('----\nfalse call')
            step_method(step_instance, renderwatch=self)

            req_args = {
                'chat_id': 'CHAT_ID_HERE',
                'message': 'MESSAGE_HERE',
            }

            part = partial(
                step_method,
                step_instance,
                renderwatch = self,
                **req_args,
            )

            # Add event handler
            handler = getattr(self.event_manager, step_instance.trigger)
            handler += partial(
                step_instance.run,
                part,
            )

            action_steps.append(step_instance)

    def main(self):
        # render jobs activity
        print('----\nEVENT 1')
        self.event_manager.event1(job='job line 163 EVENT1')
        print('----\nEVENT 2')
        self.event_manager.event2(job='job line 164 EVENT2')


if __name__ == '__main__':
    rw = Renderwatch()
    rw.main()
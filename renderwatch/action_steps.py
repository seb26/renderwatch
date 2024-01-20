from functools import partial

from renderwatch.utilities import *

class ActionStepInvalidCallback:
    def __call__(*args):
    	log(f"invalid_action_step_callback():", *args)

class ActionStep:
    def __init__(self, action, **kwargs):
        self.action = action
        data = kwargs['data']

        if data['step'] in ActionSteps.__steps__:
            step_function = ActionSteps.__steps__[data['step']]
            self.callback = partial(self.run, step_function, data=data)
        else:
            log(f"ActionStep(): \"{self.action.name}\": '{data['']}' is not a recognised step. Check spelling or help for list of steps.")
            self.callback = ActionStepInvalidCallback()

    def run(self, step_function, *args, **kwargs):
        # log('DEBUG action_steps.py:25', args)
        # log('DEBUG action_steps.py:25', kwargs)
        data = kwargs['data']
        self.action.context.event_internal.action_step_fired(data['step'], data['index'], data['settings'])
        try:
            # Run it, and pass the user's setting params
            step_function(**data['settings'])
        except Exception as e:
            log(f"ActionStep(): {self.action.name} on {data['trigger']} - tried to run step {data['step']} #{data['index']} but hit error, see:")
            log(e)

class Telegram:
    def send_message():
        log('Telegram.send_message(): perform this part of the send here.')

    def __call__(*args, **kwargs):
        log('Telegram ran call!', args, kwargs)
        Telegram.send_message()

class ActionSteps:
    __steps__ = {
        'telegram': Telegram.__call__,
    }

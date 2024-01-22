from functools import partial
import os
import traceback

import requests

from renderwatch.utilities import *

class ActionStepInvalidCallback:
    def __call__(*args):
        log(f"invalid_action_step_callback():", *args)

class ActionStep:
    def __init__(self, **kwargs):
        self.action = kwargs['action'] if 'action' in kwargs else None
        self.data = kwargs['data'] if 'data' in kwargs else None

        if 'step_type' in self.data:
            if self.data['step_type'] in ActionSteps.__steps__:
                step_library = ActionSteps.__steps__[self.data['step_type']]
                # Check if the required settings have been specified by user
                for setting, typ in step_library._required_settings_:
                    if not setting in self.data['settings']:
                        log(f"ActionStep(): \"{self.action.name}\": '{self.data['step_type']}' is missing this setting: `{setting}`.")
                    else:
                        if not isinstance(self.data['settings'][setting], typ):
                            log(f"ActionStep(): \"{self.action.name}\": '{self.data['step_type']}' make sure this setting: `{setting}` is the correct type `{typ}`.")
                # Create the callback
                step_function = step_library.__call__
                self.callback = partial(self.run, step_function)
            else:
                log(f"ActionStep(): \"{self.action.name}\": '{self.data['step_type']}' is not a recognised step. Check spelling or help for list of steps.")
                self.callback = ActionStepInvalidCallback()

    def run(self, step_function, **kwargs):
        # log('DEBUG action_steps.py:25', kwargs)
        self.job = kwargs['job'] if 'job' in kwargs else None
        self.action.context.event_internal.action_step_fired(self.data['step_type'], self.data['index'], self.data['settings'])
        # Check if user has enabled this step
        if self.action.enabled:
            try:
                # Run it, and pass the user's setting params
                step_function(
                    action = self.action,
                    step = self,
                    job = self.job,
                )
            except Exception:
                log(f"ActionStep(): {self.action.name} on {self.data['trigger']} - tried to run step {self.data['step_type']} #{self.data['index']} but hit error, see:")
                log(traceback.print_exc())

class Telegram:
    _required_settings_ = [
        ( 'chat_id', int ),
        ( 'message', str ),
    ]
    def send_message(token, chat_id, text):
        api_URL = f"https://api.telegram.org/bot{token}/sendMessage"
        request = requests.get(
            api_URL,
            params = {
                'chat_id': chat_id,
                'text': text,
            })
        log('Telegram.send_message():', request, request.url)

    def __call__(**kwargs):
        print('debug 65', kwargs)
        # Get the token from user's config
        context = kwargs['action'].context
        config = context.config['renderwatch']
        if not 'telegram' in config['steps']:
            log(f"Telegram(): there is no Telegram settings in config.yml. Correct this, we need the token to be able to do anything.")
        # Locate a token, 1 of 3 different ways
        token_sources = config['steps']['telegram']
        token = False
        token_found = False
        while not token_found:
            # 1. Using OS environment variables accessible to Python
            if 'token_environment_variable_name' in token_sources:
                token = os.environ[token_sources['token_environment_variable_name']]
                token_found = True
            # 2. Read a file that user specifies
            elif 'token_filepath' in token_sources:
                try:
                    token = open(token_sources['token_filepath'])
                    token_found = True
                except:
                    log(f"Telegram(): tried to open your token_filepath but received this error:")
                    log(traceback.print_exc())
                    break
            # 3. Or just read it plaintext from their config
            elif 'token_plaintext':
                if isinstance(token_sources['token_plaintext'], str) and token_sources['token_plaintext'] is not '':
                    token = token_sources['token_plaintext']
                    token_found = True
                else:
                    break
            else:
                break
        if not token:
            log(f"Telegram(): there were no valid tokens listed in your renderwatch.steps.telegram in config. Either specify token_environment_variable_name, token_filepath or token_plaintext.\nThis Telegram step will not be run.")
            return
        # Format the text of the message
        job = kwargs['job']
        chat_id = kwargs['step'].data['settings']['chat_id']
        text_to_format = kwargs['step'].data['settings']['message']
        message = ActionSteps.format_message(text_to_format, job=job)
        # Send
        Telegram.send_message(token, chat_id, message)
        context.event_internal.action_step_telegram_message_sent( { 'chat_id': chat_id, 'message_final': message } )

class ActionSteps:
    __steps__ = {
        'telegram': Telegram,
    }

    def format_message(text_to_format, job=None):
        output = False
        try:
            output = text_to_format.format(**job.__dict__)
        except KeyError as e:
            log(f"ActionSteps.format_message(): did not recognise this param: {e}. Check your actions.yml")
        if not output or not isinstance(output, str):
            log(f"ActionSteps.format_message(): did not create a valid output message, have a look at it:\n{output}")
        return output

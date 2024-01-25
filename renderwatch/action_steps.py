from functools import partial
import logging
import os
import traceback

import requests

from renderwatch.utilities import *

class ActionStepInvalidCallback:
    def __call__(*args):
        logging.error(f"invalid_action_step_callback():", *args)

class ActionStep:
    def __init__(self, **kwargs):
        self.renderwatch = kwargs['action'].renderwatch
        self.action = kwargs['action'] if 'action' in kwargs else None
        self.data = kwargs['data'] if 'data' in kwargs else None

        if 'step_type' in self.data:
            if self.data['step_type'] in ActionSteps.__steps__:
                step_library = ActionSteps.__steps__[self.data['step_type']]
                # Check if the required settings have been specified by user
                for setting, typ in step_library._required_settings_:
                    if not setting in self.data['settings']:
                        self.renderwatch.log.error(f"ActionStep(): \"{self.action.name}\" > '{self.data['step_type']}' is missing this setting: `{setting}`.")
                    else:
                        if not isinstance(self.data['settings'][setting], typ):
                            self.renderwatch.log.error(f"ActionStep(): \"{self.action.name}\" > '{self.data['step_type']}' make sure this setting: `{setting}` is the correct type `{typ}`.")
                # Create the callback
                step_function = step_library.__call__
                self.callback = partial(self.run, step_function)
            else:
                self.renderwatch.log.error(f"ActionStep(): \"{self.action.name}\": '{self.data['step_type']}' is not a recognised step. Check spelling or help for list of steps.")
                self.callback = ActionStepInvalidCallback()

    def run(self, step_function, **kwargs):
        self.job = kwargs['job'] if 'job' in kwargs else None
        self.renderwatch.event_internal.action_step_fired(self.data['step_type'], self.data['index'], self.data['settings'])
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
                self.renderwatch.log.error(f"ActionStep(): {self.action.name} on {self.data['trigger']} - tried to run step {self.data['step_type']} #{self.data['index']} but hit error, see:")
                self.renderwatch.log.error(traceback.print_exc())

class Telegram:
    _required_settings_ = [
        ( 'chat_id', int ),
        ( 'message', str ),
    ]
    def send_message(token, chat_id, text, logger=logging.debug):
        api_URL = f"https://api.telegram.org/bot{token}/sendMessage"
        request = requests.get(
            api_URL,
            params = {
                'chat_id': chat_id,
                'text': text,
            })
        logger(f'Telegram.send_message(): {request}')

    def __call__(**kwargs):
        # Get the token from user's config
        renderwatch = kwargs['action'].renderwatch
        config = renderwatch.config['renderwatch']
        if not 'telegram' in config['steps']:
            renderwatch.log.error(f"Telegram(): there is no Telegram settings in config.yml. Correct this, we need the token to be able to do anything.")
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
                    renderwatch.log.error(f"Telegram(): tried to open your token_filepath but received this error:")
                    renderwatch.log.error(traceback.print_exc())
                    break
            # 3. Or just read it plaintext from their config
            elif 'token_plaintext':
                if isinstance(token_sources['token_plaintext'], str) and not token_sources['token_plaintext']:
                    token = token_sources['token_plaintext']
                    token_found = True
                else:
                    break
            else:
                break
        if not token:
            renderwatch.log.error(f"Telegram(): there were no valid tokens listed in your renderwatch.steps.telegram in config. Either specify token_environment_variable_name, token_filepath or token_plaintext.\nThis Telegram step will not be run.")
            return
        # Format the text of the message
        job = kwargs['job']
        chat_id = kwargs['step'].data['settings']['chat_id']
        text_to_format = kwargs['step'].data['settings']['message']
        message = renderwatch.format_message(text_to_format, job=job)
        # Send
        Telegram.send_message(token, chat_id, message, logger=renderwatch.log.debug)
        renderwatch.event_internal.action_step_telegram_message_sent( { 'chat_id': chat_id, 'message_final': message } )

class ActionSteps:
    __steps__ = {
        'telegram': Telegram,
    }
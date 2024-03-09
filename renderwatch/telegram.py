import logging
import os

import requests

logger = logging.getLogger(__name__)

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
        logger.debug(f'Telegram.send_message(): {request}')

    def __call__(**kwargs):
        # Get the token from user's config
        renderwatch = kwargs['action'].renderwatch
        config = renderwatch.config['renderwatch']
        if not 'telegram' in config['steps']:
            logger.error(f"Telegram(): there is no Telegram settings in config.yml. Correct this, we need the token to be able to do anything.")
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
                except Exception as e:
                    logger.error(f"Telegram(): tried to open your token_filepath but received this error:")
                    logger.error(e, exc_info=1)
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
            logger.error(f"Telegram(): there were no valid tokens listed in your renderwatch.steps.telegram in config. Either specify token_environment_variable_name, token_filepath or token_plaintext.\nThis Telegram step will not be run.")
            return
        # Format the text of the message
        job = kwargs['job']
        chat_id = kwargs['step'].data['settings']['chat_id']
        text_to_format = kwargs['step'].data['settings']['message']
        message = renderwatch.format_message(text_to_format, job=job)
        # Send
        Telegram.send_message(token, chat_id, message)
        renderwatch.event_internal.action_step_telegram_message_sent( { 'chat_id': chat_id, 'message_final': message } )

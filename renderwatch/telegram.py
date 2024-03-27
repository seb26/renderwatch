from renderwatch.step import Step

import logging
from os import getenv
from pprint import pprint

import requests

logger = logging.getLogger(__name__)

class Telegram(Step):
    def __init__(self):
        super(Telegram, self).__init__()
        self.token = None

    def __validate__(
        self,
        token_env_var: str = None,
        token_filepath: str = None,
        token_plaintext: str = None,
        force: bool = False,
    ):
        if self.token and not force:
            # Already have a good token
            return True
        # Locate a token
        def _search_tokens():
            # 1. Using OS environment variables accessible to Python
            if token_env_var:
                env_var = getenv(token_env_var)
                if env_var and isinstance(env_var, str):
                    yield ( 'token_env_var', env_var )
            # 2. Read a file that user specifies
            if token_filepath:
                try:
                    token_from_file = open(token_filepath, 'r', encoding='utf-8')
                    if token_from_file and isinstance(token_from_file, str):
                        yield ( 'token_from_file', token_from_file )
                except Exception as e:
                    logger.error(f"Tried to open your token_filepath but received this error:")
                    logger.error(e, exc_info=1)
            # 3. Or just read it plaintext from their config
            if token_plaintext:
                yield ( 'token_plaintext', token_plaintext )
        token = None
        for token_type, token_value in _search_tokens():
            if Telegram.check_token_is_valid(token_value):
                logger.debug(f"This token ({token_type}) is valid")
                token = token_value
            else:
                logger.warning(f"This token ({token_type}) did not give a good response from Telegram API. Trying the next available token instead.")
                continue
        if token:
            self.token = token
            return True
        else:
            logger.error(f"There were no valid tokens listed in your renderwatch.steps.telegram in config. Either specify token_environment_variable_name, token_filepath or token_plaintext.\nThis Telegram step will not be run.")
            return False
    
    def check_token_is_valid(token):
        api_url = f"https://api.telegram.org/bot{token}/getMe"
        request = requests.get(api_url)
        if request.status_code == 200:
            if 'ok' in request.json():
                if request.json()['ok'] is True:
                    return True
        logger.warning(f"check_token_is_valid - False - request {request.text}")
        return False

    @Step.action('send_message', params=['chat_id', 'message'])
    def send_message(
        self,
        context,
        *args,
        chat_id: int,
        message: str,
        **kwargs,
    ):
        # Format the text of the message
        message_formatted = context.renderwatch.format_message_from_renderjob(
            message,
            kwargs['job'],
        )
        # Send
        api_url = f"https://api.telegram.org/bot{context.token}/sendMessage"
        request = requests.get(
            api_url,
            params = {
                'chat_id': chat_id,
                'text': message_formatted,
            },
        )
        if not request.ok:
            logger.error(f'{request} - {request.text}')

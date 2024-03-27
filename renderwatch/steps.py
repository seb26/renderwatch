from .telegram import Telegram
from .functions import Shell, VerifyOutput

from enum import Enum

class Steps(Enum):
    telegram = Telegram
    verify_output = VerifyOutput
    shell = Shell
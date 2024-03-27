from .step import Step
from pprint import pprint
from typing import Union
import logging
import subprocess

logger = logging.getLogger(__name__)

class VerifyOutput(Step):
    def __init__(self):
        super(VerifyOutput, self).__init__()
        self.token = None

    def __validate__(
        self,
        force: bool = False,
    ):
        return True
    
    @Step.action('check_file_has_complete_duration')
    def check_file_has_complete_duration(
        context,
        *args,
        **kwargs,
    ):
        rw = context.renderwatch
        job = kwargs['job']

        pprint(job.__dict__)

        look_inside = job['target_directory']

class Shell(Step):
    """Send commands to shell"""
    def __init__(self):
        super(Shell, self).__init__()

    def __validate__(
        self,
        force: bool = False,
    ):
        # So far nothing to validate here
        return True
    
    @Step.action('run_cmd', params=['cmd', 'format_job_tokens'])
    def run_cmd(
        self,
        context,
        *args,
        cmd: Union[str, list] = None,
        format_job_tokens: bool = True,
        subfolder: str = None,
        **kwargs,
    ):
        logger.debug(f'User cmd - {type(cmd)}: {cmd}')
        if isinstance(cmd, str):
            user_args = cmd.split(' ')
        elif isinstance(cmd, list):
            user_args = cmd
        else:
            logger.error(f'run_cmd(): unrecognised type of cmd {type(cmd)}')
            return
        if kwargs.get('job', False) and format_job_tokens:
            # Insert job keyvalues that user specifies
            new_user_args = []
            for arg in user_args:
                try:
                    output = arg.format(**kwargs['job'].__dict__)
                    new_user_args.append(output)
                except Exception as e:
                    logger.error(f'Unable to fill in render job keyvalues - Arg: {arg} - Exception: {e.__class__}')
                    logger.debug(e, exc_info=1)
                    return
            user_args = new_user_args
        if kwargs.get('on_exit_close_window', True):
            # Open a shell after the cmd is run, to keep the window open
            user_args[-1] += ';'
            user_args.append('zsh')
        if kwargs.get('run_in_visible_window', True):
            user_args_string = ' '.join(user_args)
            osascript_args = [
                f'tell app "Terminal" to do script "{user_args_string}"',
                'tell app "Terminal" to activate',
            ]
            cmd_args = [ 'osascript' ]
            for line in osascript_args:
                cmd_args.append('-e')
                cmd_args.append("'" + line + "'")
            cmd_args = ' '.join(cmd_args)
            shell = True
        else:
            cmd_args = user_args
            shell = False
        try:
            logger.debug(f'run_cmd(): args (type {type(cmd_args)}): {cmd_args}')
            proc = subprocess.Popen(
                cmd_args,
                shell = shell,
                stderr = subprocess.STDOUT,
                stdout = subprocess.PIPE,
            )
            proc.wait()
            stdout, stderr = proc.communicate()
            logger.debug(f'Process stdout: {stdout}')
            logger.debug(f'Process stderr: {stderr}')
            return
        except Exception as e:
            logger.error(f'Unable to run this cmd, hit exception. Command: {cmd_args} | Exception: {e}')
            logger.debug(e, exc_info=1)

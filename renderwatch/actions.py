from .exceptions import UserInvalidAction
from .step import Step
from .steps import Steps
from copy import deepcopy
from functools import partial
import itertools
import logging

logger = logging.getLogger(__name__)

class UserAction(object):
    def __init__(
        self,
        renderwatch,
        name: str,
        index: int = 0,
        enabled: bool = True,
        steps: list = [],
        triggers: list = [],
    ):
        self.renderwatch = renderwatch
        self.index = index # order it appeared in user's actions.yml
        self.name = name
        self.enabled = enabled
        self.steps = {}
        if self.enabled:
            logger.debug(f"Action {self.index} ({self.name}): evaluating user's input..")
            count_valid_steps = self._init(steps, triggers)
            logger.debug(f"Action {self.index} ({self.name}): found {count_valid_steps} valid steps for this action.")
            if count_valid_steps == 0:
                raise UserInvalidAction
        else:
            logger.debug(f"Action {self.index} ({self.name}): disabled.")

    def _init(self, steps, triggers):
        # Validate triggers
        self.triggers = set()
        for trigger in triggers:
            if trigger in self.renderwatch.event_resolve.__events__:
                self.triggers.add(trigger)
            else:
                logger.error(f"Action {self.index} ({self.name}): '{trigger}' is not a recognised trigger. Check spelling or help for list of triggers.")
        # Validate steps
        try:
            # Account for our YAML data layout, and index each step
            step_count = itertools.count(1)
            step_entries = [ (next(step_count), k, v) for step in steps for k, v in step.items() ]
        except Exception as e:
            logger.error(f"Action {self.index} ({self.name}): : could not parse steps. See below exception:")
            logger.debug(e, exc_info=1)
        count_valid_steps = 0
        for user_step_index, user_step_type, user_settings in step_entries:
            # Validate the STEP TYPE NAME
            if not user_step_type in Steps.__members__.keys():
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index} - ({user_step_type}) is not a recognised step, skipping. Check spelling or help for list of steps.")
                continue
            # Store on the action.
            self.steps[user_step_type] = {}
            # Check for a relevent field in config, if any
            if user_step_type in self.renderwatch.config['renderwatch']['steps']:
                user_config = self.renderwatch.config['renderwatch']['steps'][user_step_type]
            else:
                user_config = {}
            # Initialise a Step for it
            step_class = Steps[user_step_type].value
            # Check if we have saved a validated instance, or create one if not
            if user_step_type in self.renderwatch._validated_user_steps.keys():
                step_instance = deepcopy(self.renderwatch._validated_user_steps[user_step_type])
            else:
                step_instance = step_class()
                # Validate with the Step's own validation before proceeding
                if step_instance.__validate__(**user_config):
                    self.renderwatch._validated_user_steps[user_step_type] = step_instance
                else:
                    logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index} ({user_step_type}) - skipping, it didn't validate properly. Check you have all the correct config params for this kind of Step in config.yml.")
                    continue
            # Confirm the user specified a Keyword Action
            if not 'action' in user_settings:
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index}: an action keyword was not specified for this Step ({user_step_type}). Check spelling or help for list of steps.")
                continue
            # Validate the keyword action reflects a valid method
            if not user_settings['action'] in step_instance.methods:
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index}: '{user_settings['action']}' is not a recognised action for this Step ({user_step_type}). Check spelling or help for list of steps.")
                continue
            count_valid_steps += 1
            # Get that corresponding method
            step_action_keyword = user_settings.pop('action')
            step_method = step_instance.get_method_from_keyword(step_action_keyword)
            # Check that all required parameters are specified by user
            required_params = {}
            for param in step_instance.required_params[step_action_keyword]:
                if param not in user_settings:
                    logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index}: the setting '{param}' was not found specified on this step. Check spelling or help for list of steps.")
                    continue
                required_params[param] = user_settings.pop(param)
            # Add pointers
            step_instance.action = self
            step_instance.index = user_step_index
            step_instance.step_type = user_step_type
            step_instance.renderwatch = self.renderwatch
            for trigger in self.triggers:
                step_instance.trigger = trigger
                step_instance.signature = f'on_{trigger}.{user_step_type}.{step_action_keyword}.{step_instance.index}'
                # Create a function pointer
                executable = partial(
                    step_method,
                    step_instance, # `context`
                    **required_params,
                )
                handler_callback = partial(
                    step_instance.run,
                    executable,
                    callback_pre = self._create_sub_handler(step_instance.signature + '.pre', step_instance),
                    callback_post = self._create_sub_handler(step_instance.signature + '.post', step_instance)
                )
                handler = getattr(self.renderwatch.event_resolve, trigger)
                handler += handler_callback
                # Save it to the action
                if trigger in self.steps[step_instance.step_type]:
                    self.steps[step_instance.step_type][trigger].append(step_instance)
                else:
                    self.steps[step_instance.step_type][trigger] = [ step_instance ]
            logger.info(f"Action {self.index} ({self.name}), Step {user_step_index} ({user_step_type}): added successfully.")
        return count_valid_steps
    
    def _create_sub_handler(
        self,
        signature: str,
        instance: Step,
    ):
        """
        Given a signature, return a callback which when executed will fire an event under that signature's name
        The idea is that a Pre-run and Post-run event can be fired, when a user's step is fired
        - signature: e.g. on_render_job_started.telegram.send_message.1.pre
        """
        self.renderwatch.event_user.__events__.add(signature)
        method = getattr(self.renderwatch.event_user, signature)
        def callback():
            method(step=instance)
            logging.getLogger(f'renderwatch.user.{signature}').debug('fired')
        return callback

    def __str__(self):
        return self.name


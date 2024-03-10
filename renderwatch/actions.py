from .step import Step
from .steps import Steps

import itertools
import logging
import traceback
from copy import deepcopy
from functools import partial

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
            self._init(steps, triggers)
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
        for user_step_index, user_step_type, user_settings in step_entries:
            # Validate the STEP TYPE NAME
            if not user_step_type in Steps.__members__.keys():
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index} - ({user_step_type}) is not a recognised step. Check spelling or help for list of steps.")
            # Store on the action.
            self.steps[user_step_type] = {}
            # Validate the STEP TYPE has a field in config
            if not user_step_type in self.renderwatch.config['renderwatch']['steps']:
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index} ({user_step_type}) - there was no corresponding field in config.yml for {user_step_type}. Address that.")
            user_config = self.renderwatch.config['renderwatch']['steps'][user_step_type]
            # Initialise a Step for it
            step_class = Steps[user_step_type].value
            step_instance = step_class()
            # Validate with the Step's own validation before proceeding
            if not step_instance.__validate__(**user_config):
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index} ({user_step_type}) - skipping, it didn't validate properly. Check you have all the correct params for this kind of Step.")
                continue
            # Confirm the user specified a Keyword Action
            if not 'action' in user_settings:
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index}: an action keyword was not specified for this Step ({user_step_type}). Check spelling or help for list of steps.")
                continue
            # Validate the keyword action reflects a valid method
            if not user_settings['action'] in step_instance.methods:
                logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index}: '{user_settings['action']}' is not a recognised action for this Step ({user_step_type}). Check spelling or help for list of steps.")
                continue
            # Get that corresponding method
            step_method = step_instance.get_method_from_keyword( user_settings.pop('action') )
            # Check that all required parameters are specified by user
            required_attribs = {}
            for attrib in step_instance.required[step_instance.action_keyword]:
                if attrib not in user_settings:
                    logger.warning(f"Action {self.index} ({self.name}), Step {user_step_index}: the setting '{attrib}' was not found specified on this step. Check spelling or help for list of steps.")
                    continue
                required_attribs[attrib] = user_settings.pop(attrib)
            # Add pointers
            step_instance.action = self
            step_instance.index = user_step_index
            step_instance.step_type = user_step_type
            step_instance.renderwatch = self.renderwatch
            for trigger in self.triggers:
                step_instance.trigger = trigger
                # Create a function pointer
                executable = partial(
                    step_method,
                    step_instance, # `context`
                    **required_attribs,
                )
                handler_callback = partial(
                    step_instance.run,
                    executable,
                )
                handler = getattr(self.renderwatch.event_resolve, trigger)
                handler += handler_callback
                # Save it to the action
                if trigger in self.steps[step_instance.step_type]:
                    self.steps[step_instance.step_type][trigger].append(step_instance)
                else:
                    self.steps[step_instance.step_type][trigger] = [ step_instance ]
            logger.info(f"Action {self.index} ({self.name}), Step {user_step_index} ({user_step_type}): added successfully.")

    def __str__(self):
        return self.name


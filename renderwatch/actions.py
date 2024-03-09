from .telegram import Telegram

import itertools
import logging
import traceback
from functools import partial

logger = logging.getLogger(__name__)

class ActionStepInvalidCallback:
    def __call__(*args):
        logging.error(f"invalid_action_step_callback():", *args)

class Action:
    def __init__(self, definition, actions_filepath=False, renderwatch=None):
        self.name = definition['name']
        self.enabled = definition['enabled'] if 'enabled' in definition else True
        self.triggers = set()
        self.steps = set()

        # renderwatch
        self.renderwatch = renderwatch

        # Check if user specified a single trigger, make it a list for processing
        if isinstance(definition['triggered_by'], str):
            triggers = list(definition['triggered_by'])
        else:
            triggers = definition['triggered_by']
        for trigger in triggers:
            # Check each event is valid
            if trigger in self.renderwatch.event_resolve.__events__:
                self.triggers.add(trigger)
            else:
                logger.error(f"Action(): \"{self.name}\": '{trigger}' is not a recognised trigger. Check spelling or help for list of triggers.")
        # Account for our YAML data layout, and index each step
        try:
            step_count = itertools.count(1)
            step_entries = [ (next(step_count), k, v) for step in definition['steps'] for k, v in step.items() ]
        except Exception as e:
            logger.error(f"Action(): \"{self.name}\": could not parse steps. See below exception:")
            logger.error(e)
        # Create step callbacks so that the Steps can fire
        # We must apply to all triggers, since users are allowed to specify multiple triggers for a same set of steps
        for trigger in self.triggers:
            for index, step_type, settings in step_entries:
                # Test if a recognised step
                if step_type in ActionSteps.__steps__:
                    # Collect data to provide to the downstream functions
                    data = { 'trigger': trigger, 'index': index, 'settings': settings, 'step_type': step_type }
                    step_object = ActionStep(action=self, data=data)
                    # Save it
                    self.steps.add(step_object)
                    # Now we have a valid callback object
                    # Let's register it officially so that it can be executed with the event.
                    handler = getattr(self.renderwatch.event_resolve, trigger)
                    handler += step_object.callback
                else:
                    logger.error(f"Action(): \"{self.name}\": `{step_type}` is not a recognised step. Check spelling or help for list of steps.")
                    continue
        # User didn't specify any valid steps
        if len(self.steps) == 0:
            logger.error(f"Action(): \"{self.name}\": there were no (valid) steps for this action.")
            return

    def __str__(self):
        return self.name

class ActionSteps:
    __steps__ = {
        'telegram': Telegram,
    }

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
                        logger.error(f"ActionStep(): \"{self.action.name}\" > '{self.data['step_type']}' is missing this setting: `{setting}`.")
                    else:
                        if not isinstance(self.data['settings'][setting], typ):
                            logger.error(f"ActionStep(): \"{self.action.name}\" > '{self.data['step_type']}' make sure this setting: `{setting}` is the correct type `{typ}`.")
                # Create the callback
                step_function = step_library.__call__
                self.callback = partial(self.run, step_function)
            else:
                logger.error(f"ActionStep(): \"{self.action.name}\": '{self.data['step_type']}' is not a recognised step. Check spelling or help for list of steps.")
                self.callback = ActionStepInvalidCallback()

    def run(self, step_function, **kwargs):
        self.job = kwargs['job'] if 'job' in kwargs else None
        self.renderwatch.event_internal.action_step_fired(data=self.data)
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
                logger.error(f"ActionStep(): {self.action.name} on {self.data['trigger']} - tried to run step {self.data['step_type']} #{self.data['index']} but hit error, see:")
                logger.error(traceback.print_exc())


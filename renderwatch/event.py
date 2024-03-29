import logging
from events import Events
from functools import partial

logger = logging.getLogger(__name__)

class BaseEventGroup(Events):
    group_name = None
    events = ()

    def __init__(self):
        super(BaseEventGroup, self).__init__()
        # Name should evaluate to: renderwatch.event.group_name
        self.logger = logging.getLogger(__name__ + '.' + self.group_name)
        for event_name in self.__events__:
            # Get a handler per this event name
            handler = getattr(self, event_name)
            # Attach some log wrappers
            handler += partial(self.log, event_name)
            handler += partial(self.debug_data, event_name)

    def log(self, event_name, *args, **kwargs):
        if kwargs.get('job'):
            self.logger.info(f"{kwargs['job'].id[:8]} | {event_name}")
        else:
            self.logger.info(f"{event_name}")
            
    
    def debug_data(self, event_name, *args, **kwargs):
        if 'data' in kwargs:
            self.logger.debug(f"{event_name} - Data: {kwargs['data']}")

# Events
class ResolveEvents(BaseEventGroup):
    group_name = 'resolve'
    __events__ = (
        'api_conn_initial_success',
        'api_conn_lost',
        'project_onload',
        'project_change',
        'db_onload',
        'db_change',
        'render_job_onload',
        'render_job_change_misc',
        'render_job_new',
        'render_job_removed',
        'render_job_started',
        'render_job_progress',
        'render_job_progress_initial_update',
        'render_job_completed',
        'render_job_cancelled',
        'render_job_failed',
        'render_job_reset',
    )

class InternalEvents(BaseEventGroup):
    group_name = 'internal'
    __events__ = (
        'action_step_fired',
        'action_step_telegram_message_sent',
    )

class UserEvents(BaseEventGroup):
    group_name = 'user'
    # no events to define - they are dynamically defined
    __events__ = set()
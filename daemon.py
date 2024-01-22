# builtins
import datetime
import itertools
from functools import partial
import locale
import pprint
import time
import sys
import uuid

# pip libraries
import dictdiffer
from events import Events
import humanize
from pydavinci import davinci
import yaml
import yamale

# renderwatch
from renderwatch.action_steps import *
from renderwatch.utilities import *

# Globals
RENDERWATCH_DEFAULT_API_POLL_TIME = 2 
RENDERWATCH_DEFAULT_CONFIG_FILEPATH = 'config.yml'
RENDERWATCH_DEFAULT_ACTIONS_FILEPATH = 'actions.yml'

# Objects
class Action:
    def __init__(self, context, definition, actions_filepath=False):
        self.name = definition['name']
        self.enabled = definition['enabled'] if 'enabled' in definition else True
        self.triggers = set()
        self.steps = set()

        # renderwatch
        self.context = context

        # Check if user specified a single trigger, make it a list for processing
        if isinstance(definition['triggered_by'], str):
            triggers = list(definition['triggered_by'])
        else:
            triggers = definition['triggered_by']
        for trigger in triggers:
            # Check each event is valid
            if trigger in self.context.event_resolve.__events__:
                self.triggers.add(trigger)
            else:
                log(f"Action(): \"{self.name}\": '{trigger}' is not a recognised trigger. Check spelling or help for list of triggers.")
        # Account for our YAML data layout, and index each step
        try:
            step_count = itertools.count(1)
            step_entries = [ (next(step_count), k, v) for step in definition['steps'] for k, v in step.items() ]
        except Exception as e:
            log(f"Action(): \"{self.name}\": could not parse steps. See below exception:")
            log(e)
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
                    handler = getattr(self.context.event_resolve, trigger)
                    handler += step_object.callback
                else:
                    log(f"Action(): \"{self.name}\": `{step_type}` is not a recognised step. Check spelling or help for list of steps.")
                    continue
        # User didn't specify any valid steps
        if len(self.steps) == 0:
            log(f"Action(): \"{self.name}\": there were no (valid) steps for this action.")
            return

    def __str__(self):
        return self.name

class RenderJob:
    def __init__(self, job_dump, render_status_info, time_collected):
        time_collected = datetime.datetime.now()
        self.last_touched = False

        jid = job_dump['JobId']
        self.id = jid
        self.history = []

        # Defaults
        self.name = None
        self.target_directory = None
        self.timeline_name = None
        self.status = None
        self.completion_percent = None
        self.time_elapsed = None
        self.time_remaining = None

        # Run first time
        self.update(job_dump, render_status_info, time_collected)

    def update(self, job_dump, render_status_info, time_collected):
        # Convert to integer for internal use
        timestamp = int(time_collected.timestamp())
        self.timestamp_short = time_collected.strftime('%H:%M:%S')
        # Add some defaults, to make comparing new values easier
        job_dump.update({
            'TimeTakenToRenderInMs': False,
            'EstimatedTimeRemainingInMs': False,
            'CompletionPercentage': False,
            'Error': False,
        })
        # Combine render_status into the job_dump, since it has unique k/vs
        job_dump.update(render_status_info)
        # Create a new history entry marked by time
        def _create_history_entry(timestamp):
            obj = {
                'id': job_dump['JobId'],
                'time': time_collected,
                'job': job_dump,
            }
            self.history.append( (timestamp, obj ) )
            # TODO - NEED TO DELETE OLD HISTORY ENTRIES !!!!!!!!!*********
            return 
        # Set/overwrite attribs with the latest job dump info
        self.name = job_dump['RenderJobName']
        self.target_directory = job_dump['TargetDir']
        self.timeline_name = job_dump['TimelineName']
        self.status = job_dump['JobStatus']
        # Interpret these values a bit
        if job_dump['CompletionPercentage']:
            self.completion_percent = str(job_dump['CompletionPercentage']) + '%'
        if job_dump['TimeTakenToRenderInMs']:
            amount = datetime.timedelta(milliseconds=job_dump['TimeTakenToRenderInMs'])
            self.time_elapsed = humanize.precisedelta(time_collected, suppress=['days'])
        if job_dump['EstimatedTimeRemainingInMs']:
            amount = datetime.timedelta(milliseconds=job_dump['EstimatedTimeRemainingInMs'])
            self.time_remaining = humanize.precisedelta(time_collected, suppress=['days'])
        # Mark that we checked this
        self.last_touched = timestamp
        # If first record of this job
        if len(self.history) == 0:
            _create_history_entry(timestamp)
            return True
        else:
            # Familiar job
            # So check if the job dump contents has changed in any way
            latest = max(self.history)
            latest_job = latest[1]['job']
            if latest_job == job_dump:
                # Nothing changed - don't do any further work
                return False
            else:
                # It did change!
                # TODO: Use a Try here, to handle any unexpected variances in the dicts
                # that might come from the API.
                diff_result = dictdiffer.diff(latest_job, job_dump)
                # Preprocess the results for convenience
                diff = { 'add': {}, 'change': {}, 'remove': {} }
                for d_type, param, values in diff_result:
                    diff[d_type].update( { param: values })
                # First check if any of the other vars changed at all, at this time
                data = { a:diff['change'][a][1] for a in diff['change'] if a != 'JobStatus' }
                # Then continue identification of what happened
                event_fired = False
                if 'JobStatus' in diff['change']:
                    old, new = diff['change']['JobStatus']
                    # Update internal status
                    self.status = new
                    if old == 'Ready' and new == 'Rendering':
                        renderwatch.event_resolve.render_job_started(job=self)
                        event_fired = True
                    elif old == 'Complete' and new == 'Rendering':
                        renderwatch.event_resolve.render_job_started(job=self)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Complete':
                        renderwatch.event_resolve.render_job_completed(job=self)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Cancelled':
                        renderwatch.event_resolve.render_job_cancelled(job=self)
                        event_fired = True
                    elif old and new == 'Ready':
                        renderwatch.event_resolve.render_job_reset(job=self)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Failed':
                        renderwatch.event_resolve.render_job_failed(job=self)
                        event_fired = True
                if not event_fired:
                    # No status change, but just an update to Progress
                    if 'CompletionPercentage' in diff['change']:
                        # Don't report false or zeros
                        if diff['change']['CompletionPercentage'][1]:
                            self.completion_percent = diff['change']['CompletionPercentage'][1]
                            renderwatch.event_resolve.render_job_progress(job=self)
                            event_fired = True
                if not event_fired:
                    # All other unrecognised changes
                    renderwatch.event_resolve.render_job_change_misc(job=self)
                # Save a new history entry
                _create_history_entry(timestamp)
                return True

    def dump(self):
        # Return the most recent data dump about the job
        return max(self.history)

    def __str__(self):
        return self.name

# Events
class ResolveEvents(Events):
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
        'render_job_completed',
        'render_job_cancelled',
        'render_job_failed',
        'render_job_reset',
    )

class InternalEvents(Events):
    __events__ = (
        'action_step_fired',
        'action_step_telegram_message_sent',
    )

# Program
class RenderWatch:
    
    def __init__(self,
        config_filepath=RENDERWATCH_DEFAULT_CONFIG_FILEPATH,
        actions_filepath=RENDERWATCH_DEFAULT_ACTIONS_FILEPATH ):
        # Create event handlers
        self.event_resolve = ResolveEvents()
        self.event_internal = InternalEvents()

        self.resolve = False
        self.current_project = { }
        self.current_db = False

        self.render_jobs = {}
        self.render_jobs_first_run = True

        # Parse config
        stream = open(config_filepath, 'r')
        config = yaml.safe_load(stream)
        self.config = config

        # Parse actions
        self.actions = []
        self.read_actions(actions_filepath)

    def read_actions(self, actions_filepath=RENDERWATCH_DEFAULT_ACTIONS_FILEPATH):
        # Validation schema
        actions_schema = yamale.make_schema('./schema/actions.yml')
        # Open actions
        actions_raw_text = open(actions_filepath, 'r', encoding='utf-8').read()
        actions_raw = yamale.make_data(content=actions_raw_text)
        # Validate
        try:
            yamale.validate(actions_schema, actions_raw)
            log('Actions validated OK 👍 File:', actions_filepath)
        except Exception as e:
            log(e)
            return False
        # Workaround Yamale which wraps its parsing in a list and a tuple
        # https://github.com/23andMe/Yamale/blob/master/yamale/yamale.py:32 @ ca60752
        actions = False
        if isinstance(actions_raw, list):
            if len(actions_raw) > 0:
                if isinstance(actions_raw[0], tuple):
                    if actions_raw[0][0] is not None:
                        # And then the heading for actions, which is part of our yaml schema just for readability
                        if 'actions' in actions_raw[0][0]:
                            actions = actions_raw[0][0]['actions']
        if not actions:
            log('Actions block was unreadable:', actions_raw)
            return False
        # Finish by creating new Action objects
        for definition in actions:
            self.actions.append( Action(self, definition) )

    def _get_resolve(self):
        try:
            davinci
        except:
            log("Error: pydavinci wasn't available. Is it installed correctly via pip?")
            return False    
        Resolve = davinci.Resolve()
        if Resolve._obj:
            # Identify project or database change - start by assuming no change
            self.project_was_changed = False
            self.db_was_changed = False
            data = { 'project': Resolve.project.name }
            if self.current_project:
                if Resolve.project.name != self.current_project.name:
                    # Project has changed - only coming from name.
                    self.project_was_changed = True
                    self.event_resolve.project_change(Resolve.project, data)
                    self.current_project = Resolve.project
                    self.clear_render_jobs()
            else:
                # First time load of a project
                self.current_project = Resolve.project
                self.project_was_changed = False
                self.event_resolve.project_onload(Resolve.project, data)
            data = Resolve.project_manager.db
            if self.current_db:
                if Resolve.project_manager.db != self.current_db:
                    # Database has changed
                    self.db_was_changed = True
                    self.event_resolve.db_change(Resolve, data)
                    self.current_db = Resolve.project_manager.db
                    self.clear_render_jobs()
            else:
                # First time load of a db
                self.current_db = Resolve.project_manager.db
                self.event_resolve.db_onload(Resolve, data)
                self.db_was_changed = False
            # Different jobs behaviour if there was a change
            if self.project_was_changed or self.db_was_changed:
                self.render_jobs_first_run = True
            # Save the rest of the call
            self.resolve = Resolve
            return True
        else:
            log("Error: pydavinci could not connect to Resolve API. Is Resolve running?")
            return False

    def clear_render_jobs(self):
        self.render_jobs = {}

    def update_render_jobs(self):
        # Query the API
        self._get_resolve()
        if not self.resolve:
            log('Error: Skipping update_render_jobs. No Resolve available.')
        # Mark the jobs with time that this call was made
        time_collected = datetime.datetime.now()
        timestamp = int(time_collected.timestamp())
        # Save the jobs as an ongoing database
        for job_dump in self.resolve.project.render_jobs:
            if not 'JobId' in job_dump:
                continue
            # Store them by ID
            jid = job_dump['JobId']
            # Lookup render status
            render_status_info = self.resolve.project.render_status(jid)
            # Create a new instance so we can track history of job status by time
            if not jid in self.render_jobs:
                # Save the job
                self.render_jobs[jid] = RenderJob(job_dump, render_status_info, time_collected)
                if self.render_jobs_first_run:
                    self.event_resolve.render_job_onload(job=self.render_jobs[jid])
                else:
                    self.event_resolve.render_job_new(job=self.render_jobs[jid])
            else:
                # Already a job under this ID - update its history
                self.render_jobs[jid].update(job_dump, render_status_info, time_collected)
        # Reset first time behaviour
        self.render_jobs_first_run = False
        # Locate deleted jobs. They have an older API last touched timestamp, than our current time.
        delete_these_jobs = []
        for jid, job in self.render_jobs.items():
            if job.last_touched < timestamp:
                self.event_resolve.render_job_removed()
                # Mark for deletion
                delete_these_jobs.append(jid)
        # Apply deletion from our records
        for job in delete_these_jobs:
            self.render_jobs.pop(job)

# Daemon
if __name__ == '__main__':
    log('Welcome.')
    log('Python:', sys.version, locale.getdefaultlocale())
    log('Resolve API being polled every (seconds):', RENDERWATCH_DEFAULT_API_POLL_TIME)

    renderwatch = RenderWatch()

    # TODO: Expand into proper logging with levels
    # Attach logging to every event
    def log_event(event_name, data=None, *args, **kwargs):
        log(f"({event_name})", 'args:', args, 'kwargs:', kwargs, 'data:', data)
    # Logging for Resolve render job events
    for event_name in renderwatch.event_resolve.__events__:
        handler = getattr(renderwatch.event_resolve, event_name)
        handler += partial(log_event, event_name)
    # Internal program logging
    for event_name in renderwatch.event_internal.__events__:
        handler = getattr(renderwatch.event_internal, event_name)
        handler += partial(log_event, event_name)


    while True:
        if renderwatch._get_resolve():
            renderwatch.update_render_jobs()
            pass

        time.sleep(renderwatch.config['renderwatch_daemon']['API_poll_time'])
            
# builtins
import asyncio
import datetime
import itertools
from functools import partial
import locale
import logging
import logging.config
import math
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
                self.renderwatch.log.error(f"Action(): \"{self.name}\": '{trigger}' is not a recognised trigger. Check spelling or help for list of triggers.")
        # Account for our YAML data layout, and index each step
        try:
            step_count = itertools.count(1)
            step_entries = [ (next(step_count), k, v) for step in definition['steps'] for k, v in step.items() ]
        except Exception as e:
            self.renderwatch.log.error(f"Action(): \"{self.name}\": could not parse steps. See below exception:")
            self.renderwatch.log.error(e)
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
                    self.renderwatch.log.error(f"Action(): \"{self.name}\": `{step_type}` is not a recognised step. Check spelling or help for list of steps.")
                    continue
        # User didn't specify any valid steps
        if len(self.steps) == 0:
            self.renderwatch.log.error(f"Action(): \"{self.name}\": there were no (valid) steps for this action.")
            return

    def __str__(self):
        return self.name

class RenderJob:
    def __init__(self):
        # Defaults
        self.name = None
        self.history = []
        self.target_directory = None
        self.timeline_name = None
        self.status = None
        self.completion_percent = None
        self.progress_initial_update = True
        self.job_frame_count = None
        self.time_elapsed = None
        self.time_remaining = None

        self.line_average_fps = ''
        self.line_completion_percent = ''
        self.line_time_elapsed = ''
        self.line_time_remaining = ''

    async def _init(self, job_dump, render_status_info, time_collected, renderwatch=None):
        self.renderwatch = renderwatch
        time_collected = datetime.datetime.now()
        self.last_touched = False

        jid = job_dump['JobId']
        self.id = jid
        await self.update(job_dump, render_status_info, time_collected)
        return self

    async def update(self, job_dump, render_status_info, time_collected):
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
            if self.completion_percent == 100:
                self.line_completion_percent = f"\nJob completion was: {self.completion_percent}"
        if job_dump['EstimatedTimeRemainingInMs']:
            amount = datetime.timedelta(milliseconds=job_dump['EstimatedTimeRemainingInMs'])
            self.time_remaining = humanize.precisedelta(amount, suppress=['days'])
        if self.time_remaining and self.completion_percent:
            self.line_time_remaining = f"\n{self.completion_percent} - Remaining: ~{self.time_remaining}"
        if job_dump['TimeTakenToRenderInMs']:
            amount = datetime.timedelta(milliseconds=job_dump['TimeTakenToRenderInMs'])
            self.time_elapsed = humanize.precisedelta(amount, suppress=['days'])
            self.line_time_elapsed = f"\nRender time was: {self.time_elapsed}"
            # Calculate average FPS for job
            if 'MarkIn' in job_dump and 'MarkOut' in job_dump:
                self.job_frame_count = job_dump['MarkOut'] - job_dump['MarkIn'] + 1
                self.job_average_fps = math.floor(self.job_frame_count / amount.seconds)
                self.line_average_fps = f'\nRender speed (avg): ~{self.job_average_fps} FPS'

        
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
                        self.renderwatch.event_resolve.render_job_started(job=self)
                        event_fired = True
                    elif old == 'Complete' and new == 'Rendering':
                        self.renderwatch.event_resolve.render_job_started(job=self)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Complete':
                        self.renderwatch.event_resolve.render_job_completed(job=self)
                        event_fired = True
                        # For multiple jobs queued, need to catch the next item, so check again 
                        # await self.renderwatch.follow_up_update_render_jobs()
                    elif old == 'Rendering' and new == 'Cancelled':
                        self.renderwatch.event_resolve.render_job_cancelled(job=self)
                        event_fired = True
                    elif old and new == 'Ready':
                        self.renderwatch.event_resolve.render_job_reset(job=self)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Failed':
                        self.renderwatch.event_resolve.render_job_failed(job=self)
                        event_fired = True
                if not event_fired:
                    # No status change, but just an update to Progress
                    if 'CompletionPercentage' in diff['change']:
                        # Don't report false or zeros
                        if diff['change']['CompletionPercentage'][1]:
                            self.completion_percent = diff['change']['CompletionPercentage'][1]
                            if self.progress_initial_update:
                                # Fire once for users opting for one update and not again
                                self.renderwatch.event_resolve.render_job_progress_initial_update(job=self)
                                self.progress_initial_update = False
                            self.renderwatch.event_resolve.render_job_progress(job=self)
                            event_fired = True
                if not event_fired:
                    # All other unrecognised changes
                    self.renderwatch.event_resolve.render_job_change_misc(job=self)
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
        'render_job_progress_initial_update',
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
        # Set up logging first
        log_config_yaml = yaml.safe_load( open('./logging.yml', 'r', encoding='utf-8') )
        logging.config.dictConfig(log_config_yaml)
        self.log = logging.getLogger('renderwatch')
        self.log_resolve = logging.getLogger('renderwatch_resolve_events')

        # Create event handlers
        self.event_resolve = ResolveEvents()
        self.event_internal = InternalEvents()
        # Attach a Logging event for each - going out to console & file
        for event_name in self.event_resolve.__events__:
            handler = getattr(self.event_resolve, event_name)
            handler += partial(self._log_event, event_name)
        for event_name in self.event_internal.__events__:
            handler = getattr(self.event_internal, event_name)
            handler += partial(self._log_event, event_name)

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

    def _log_event(self, event_name, data=None, *args, **kwargs):
        data_display = f" - Data: {data}" if data else ''
        self.log_resolve.info(f"{event_name}{data_display}") # For debug, include args, kwargs

    async def _connect_resolve(self):
        try:
            davinci
        except:
            self.log.critical("Error: pydavinci wasn't available. Is it installed correctly via pip?")
            return False
        Resolve = davinci.Resolve()
        if Resolve._obj is None:
            self.log.error("Resolve API is not available. Ensure Resolve is launched.")
            return False
        else:
            if Resolve._obj is None:
                self.log.error("Resolve API is not available, Resolve is not running anymore.")
                return False
            else:
                return Resolve

    async def _get_resolve(self):
        Resolve = await self._connect_resolve()
        if not Resolve:
            # No valid Resolve object
            return False
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
                await self.clear_render_jobs()
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
                await self.clear_render_jobs()
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
    
    async def _clear_old_jobs(self, timestamp):
        # Locate deleted jobs. They would have an older API last touched timestamp, than our current time.
        delete_these_jobs = []
        for jid, job in self.render_jobs.items():
            if job.last_touched < timestamp:
                self.event_resolve.render_job_removed()
                # Mark for deletion
                delete_these_jobs.append(jid)
        # Apply deletion from our records
        for job in delete_these_jobs:
            self.render_jobs.pop(job)
    
    async def create_render_job(self, jid, job_dump, render_status_info, time_collected):
        this_job = RenderJob()
        await this_job._init(job_dump, render_status_info, time_collected, renderwatch=self)
        self.render_jobs[jid] = this_job

    async def clear_render_jobs(self):
        self.render_jobs = {}

    async def update_render_jobs(self):
        # Query the API
        await self._get_resolve()
        if not self.resolve:
            self.log.error('update_render_jobs(): No Resolve available, skipping.')
            return False
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
            if jid in self.render_jobs:
                # Already a job under this ID - update its history
                await self.render_jobs[jid].update(job_dump, render_status_info, time_collected)
            else:
                # Save the job
                await self.create_render_job(jid, job_dump, render_status_info, time_collected)
                this_job = self.render_jobs[jid]
                if self.render_jobs_first_run:
                    self.event_resolve.render_job_onload(job=this_job)
                else:
                    self.event_resolve.render_job_new(job=this_job)
        # End of our first run
        self.render_jobs_first_run = False
        # Run clear jobs
        if not self.render_jobs_first_run:
            await self._clear_old_jobs(timestamp)

    async def follow_up_update_render_jobs(self):
        time.sleep(0.5)
        await self.update_render_jobs()
        
    def read_actions(self, actions_filepath=RENDERWATCH_DEFAULT_ACTIONS_FILEPATH):
        # Validation schema
        actions_schema = yamale.make_schema('./schema/actions.yml')
        # Open actions
        actions_raw_text = open(actions_filepath, 'r', encoding='utf-8').read()
        actions_raw = yamale.make_data(content=actions_raw_text)
        # Validate
        try:
            yamale.validate(actions_schema, actions_raw)
            self.log.debug('Actions validated OK 👍 File: %s', actions_filepath)
        except Exception as e:
            self.log.error(e)
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
            self.log.error('Actions block was unreadable: %s', actions_raw)
            return False
        # Finish by creating new Action objects
        for definition in actions:
            self.actions.append( Action(definition, renderwatch=self) )

    def format_message(self, text_to_format, job=None):
        output = False
        try:
            output = text_to_format.format(**job.__dict__)
        except KeyError as e:
            self.log.error("format_message(): did not recognise this param: %s. Check your actions.yml", e)
        if not output or not isinstance(output, str):
            self.log.error("format_message(): did not create a valid output message, have a look at it: \n%s",output)
        return output


# Daemon
async def main():
    logging.debug('Welcome. Python:', sys.version, locale.getdefaultlocale())

    renderwatch = RenderWatch()

    while True:
        await renderwatch.update_render_jobs()

        time.sleep(renderwatch.config['renderwatch_daemon']['API_poll_time'])

if __name__ == "__main__":
    asyncio.run(main())
            
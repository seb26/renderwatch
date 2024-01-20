# builtins
import datetime
from functools import partial
import pprint
import time
import sys
import uuid

# pip libraries
import dictdiffer
from events import Events
from pydavinci import davinci
import yaml
import yamale

# renderwatch
from renderwatch import steps
from renderwatch.utilities import *

# Globals
RENDERWATCH_DEFAULT_API_POLL_TIME = 2 
RENDERWATCH_DEFAULT_CONFIG_FILEPATH = 'config.yml'
RENDERWATCH_DEFAULT_ACTIONS_FILEPATH = 'actions.yml'

# Exceptions
class RenderWatchException(Exception):
    pass

class RenderWatchActions_Exception(Exception):
    pass

class RenderWatchActions_Invalid(RenderWatchActions_Exception):
    def __init__(self, value, context, filepath):
        try:
            context_display = f"\nContext: \"{str(context)[:64]}..." 
        except:
            context_display = None
        super().__init__(f"This action definition is invalid or missing a value: \"{value}\"{context_display}\nIn file: {filepath}")
    pass

class RenderWatchActions_InvalidTrigger(RenderWatchActions_Exception):
    def __init__(self, value, context, filepath):
        super().__init__(f"This trigger is not a valid trigger - check it or see help: \"{value}\"{context_display}\nIn file: {filepath}")
    pass

# Objects
class Action:
    def __init__(self, definition, actions_filepath=False):
        # Type checking
        if not 'name' in definition:
            raise RenderWatchActions_Invalid('name', definition, actions_filepath)
        if not 'enabled' in definition:
            raise RenderWatchActions_Invalid('enabled', definition, actions_filepath)
        if not 'triggered_by' in definition:
            raise RenderWatchActions_Invalid('triggered_by', definition, actions_filepath)
        else:
            if not isinstance(definition['triggered_by'], dict):
                raise RenderWatchActions_Invalid('triggered_by', definition, actions_filepath)

        self.name = definition['name']
        self.enabled = definition['enabled']
        self.triggers = set()

        for trigger in definition['triggered_by']:
        	# Check each event is valid
            if trigger in RenderEvents.__events__:
                self.triggers.add(trigger)
            else:
                raise RenderWatchActions_InvalidTrigger(trigger, definition, actions_filepath)



class RenderJob:
    def __init__(self, job_dump, render_status_info, time_collected):
        time_collected = datetime.datetime.now()
        jid = job_dump['JobId']
        self.id = jid
        self.history = {}
        self.last_touched = False

        # Run first time
        self.update(job_dump, render_status_info, time_collected)

    def _set_own_attribs(self, job_dump):
        # Set some parameters
        self.name = job_dump['RenderJobName']
        self.target_directory = job_dump['TargetDir']
        self.timeline_name = job_dump['TimelineName']
        self.status = job_dump['JobStatus']
        self.completion_percent = job_dump['CompletionPercentage']

    def update(self, job_dump, render_status_info, time_collected):
        # Convert to integer for internal use
        timestamp = int(time_collected.timestamp())
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
        def _create_history_entry():
            return {
                'id': job_dump['JobId'],
                'time': time_collected,
                'job': job_dump,
            }
        # Set/overwrite attribs with the latest job dump info
        self._set_own_attribs(job_dump)
        # Mark that we checked this
        self.last_touched = timestamp
        # If first record of this job
        if len(self.history) == 0:
            self.history[timestamp] = _create_history_entry()
            return True
        else:
            # Familiar job
            # So check if the job dump contents has changed in any way
            latest = max(self.history)
            latest_job = self.history[latest]['job']
            if latest_job == job_dump:
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
                event_fired = False
                # First check if any of the other vars changed at all, at this time
                data = { a:diff['change'][a][1] for a in diff['change'] if a != 'JobStatus' }
                # Then continue identification of what happened
                if 'JobStatus' in diff['change']:
                    old, new = diff['change']['JobStatus']
                    data['JobStatus'] = new
                    if old == 'Ready' and new == 'Rendering':
                        events.handler.render_job_started(self, data)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Complete':
                        events.handler.render_job_completed(self, data)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Cancelled':
                        events.handler.render_job_cancelled(self, data)
                        event_fired = True
                    elif old and new == 'Ready':
                        events.handler.render_job_reset(self, data)
                        event_fired = True
                    elif old == 'Rendering' and new == 'Failed':
                        events.handler.render_job_failed(self, data)
                        event_fired = True
                if not event_fired:
                    # No status change, but just an update to Progress
                    if 'CompletionPercentage' in diff['change']:
                        # Don't report false or zeros
                        if diff['change']['CompletionPercentage'][1]:
                            events.handler.render_job_progress(self, data)
                            event_fired = True
                if not event_fired:
                    # All other unrecognised changes
                    events.handler.render_job_change_misc(self, data)
                # Save a new history entry
                self.history[timestamp] = _create_history_entry()
                return True

    def dump(self):
        # Return the most recent data dump about the job
        latest = max(self.history)
        return self.history[latest]

    def __str__(self):
        return self.name

# Events
class RenderEvents(Events):
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

# Program
class RenderWatch:
    
    def __init__(self, actions_filepath=RENDERWATCH_DEFAULT_ACTIONS_FILEPATH):
        self.resolve = False
        self.current_project = { }
        self.current_db = False

        self.render_jobs = {}
        self.render_jobs_first_run = True

        # Parse config
        stream = open(RENDERWATCH_DEFAULT_CONFIG_FILEPATH, 'r')
        config = yaml.safe_load(stream)

        # Parse actions
        self.actions = set()
        self.read_actions(actions_filepath)

    def read_actions(self, filepath=RENDERWATCH_DEFAULT_ACTIONS_FILEPATH):
        # Validation schema
        actions_schema = yamale.make_schema('./schema/actions.yml')
        # Open actions
        actions = yamale.make_data(filepath)
        # Validate
        try:
            yamale.validate(actions_schema, actions)
        except Exception as e:
            log(e)
            return False

        # Create action objects
        for action in actions:
            try:
                obj = Action(action, filepath)
                self.actions.add(obj)
            except Exception as e:
                log(e)
                continue

        # Debug
        pp(self.actions)



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
                    events.handler.project_change(Resolve.project, data)
                    self.current_project = Resolve.project
                    self.clear_render_jobs()
            else:
                # First time load of a project
                self.current_project = Resolve.project
                self.project_was_changed = False
                events.handler.project_onload(Resolve.project, data)
            data = Resolve.project_manager.db
            if self.current_db:
                if Resolve.project_manager.db != self.current_db:
                    # Database has changed
                    self.db_was_changed = True
                    events.handler.db_change(Resolve, data)
                    self.current_db = Resolve.project_manager.db
                    self.clear_render_jobs()
            else:
                # First time load of a db
                self.current_db = Resolve.project_manager.db
                events.handler.db_onload(Resolve, data)
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
        log('Cleared render jobs')

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
                if self.render_jobs_first_run:
                    events.handler.render_job_onload(self)
                else:
                    events.handler.render_job_new(self)
                # Save the job
                self.render_jobs[jid] = RenderJob(job_dump, render_status_info, time_collected)
            else:
                # Already a job under this ID - update its history
                self.render_jobs[jid].update(job_dump, render_status_info, time_collected)
        # Reset first time behaviour
        self.render_jobs_first_run = False
        # Locate deleted jobs. They have an older API last touched timestamp, than our current time.
        delete_these_jobs = []
        for jid, job in self.render_jobs.items():
            if job.last_touched < timestamp:
                events.handler.render_job_removed(self)
                # Mark for deletion
                delete_these_jobs.append(jid)
        # Apply deletion from our records
        for job in delete_these_jobs:
            self.render_jobs.pop(job)

# Daemon
if __name__ == '__main__':
    log('Welcome.')
    log('Python:', sys.version)
    log('Resolve API being polled every (seconds):', RENDERWATCH_DEFAULT_API_POLL_TIME)
    renderwatch = RenderWatch()
    events = RenderEvents()

    # TODO: Expand into proper logging with levels
    # Attach logging to every event
    def log_event(event_name, obj, data):
    	log(f"({event_name})", obj, '- data:', data)
    for event_name in RenderEvents.__events__:
        setattr(
            events,
            event_name,
            partial(
                log_event,
                event_name
            )
        )


    while True:
        """
        if renderwatch._get_resolve():
            renderwatch.update_render_jobs()
            pass
        """

        time.sleep(RENDERWATCH_DEFAULT_API_POLL_TIME)
            


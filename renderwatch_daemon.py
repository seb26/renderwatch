from renderwatch.actions import Action
from renderwatch.event import InternalEvents, ResolveEvents
from renderwatch.renderjob import RenderJob

import asyncio
import datetime
import locale
import logging
import logging.config
import time
import sys

import yaml
from pydavinci import davinci
import yamale

# Globals
RENDERWATCH_DEFAULT_API_POLL_TIME = 2 
RENDERWATCH_DEFAULT_CONFIG_FILEPATH = 'config.yml'
RENDERWATCH_DEFAULT_ACTIONS_FILEPATH = 'actions.yml'

logger = logging.getLogger(__name__)

# Program
class RenderWatch:
    def __init__(self,
        config_filepath=RENDERWATCH_DEFAULT_CONFIG_FILEPATH,
        actions_filepath=RENDERWATCH_DEFAULT_ACTIONS_FILEPATH ):
        # Set up logging first
        log_config_yaml = yaml.safe_load( open('./logging.yml', 'r', encoding='utf-8') )
        logging.config.dictConfig(log_config_yaml)

        self.event_internal = InternalEvents()
        self.event_resolve = ResolveEvents()

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

    async def _connect_resolve(self):
        try:
            davinci
        except:
            logger.critical("Error: pydavinci wasn't available. Is it installed correctly via pip?")
            return False
        Resolve = davinci.Resolve()
        if Resolve._obj is None:
            logger.error("Resolve API is not available. Ensure Resolve is launched.")
            return False
        else:
            if Resolve._obj is None:
                logger.error("Resolve API is not available, Resolve is not running anymore.")
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
                self.event_resolve.project_change(Resolve.project, data=data)
                self.current_project = Resolve.project
                await self.clear_render_jobs()
        else:
            # First time load of a project
            self.current_project = Resolve.project
            self.project_was_changed = False
            self.event_resolve.project_onload(Resolve.project, data=data)
        data = Resolve.project_manager.db
        if self.current_db:
            if Resolve.project_manager.db != self.current_db:
                # Database has changed
                self.db_was_changed = True
                self.event_resolve.db_change(Resolve, data=data)
                self.current_db = Resolve.project_manager.db
                await self.clear_render_jobs()
        else:
            # First time load of a db
            self.current_db = Resolve.project_manager.db
            self.event_resolve.db_onload(Resolve, data=data)
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
            logger.error('update_render_jobs(): No Resolve available, skipping.')
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
            logger.debug('Actions validated OK 👍 File: %s', actions_filepath)
        except Exception as e:
            logger.error(e)
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
            logger.error('Actions block was unreadable: %s', actions_raw)
            return False
        # Finish by creating new Action objects
        for definition in actions:
            self.actions.append( Action(definition, renderwatch=self) )

    def format_message(self, text_to_format, job=None):
        output = False
        try:
            output = text_to_format.format(**job.__dict__)
        except KeyError as e:
            logger.error("format_message(): did not recognise this param: %s. Check your actions.yml", e)
        if not output or not isinstance(output, str):
            logger.error("format_message(): did not create a valid output message, have a look at it: \n%s",output)
        return output


# Daemon
async def main():
    logger.debug('Welcome. Python:', sys.version, locale.getdefaultlocale())
    renderwatch = RenderWatch()
    while True:
        await renderwatch.update_render_jobs()
        time.sleep(renderwatch.config['renderwatch_daemon']['API_poll_time'])

if __name__ == "__main__":
    asyncio.run(main())
            
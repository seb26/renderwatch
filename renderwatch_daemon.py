from renderwatch.actions import UserAction
from renderwatch.event import InternalEvents, ResolveEvents, UserEvents
from renderwatch.exceptions import UserInvalidAction, UserInvalidStep
from renderwatch.renderjob import RenderJob

import asyncio
import datetime
import locale
import logging
import logging.config
import time
import sys
from os import path

import platformdirs
from pydavinci import davinci
import yaml
import yamale


logger = logging.getLogger('renderwatch.daemon')

# Program
class RenderWatch:
    def __init__(self):
        # Inside app dist
        self.app_dirpath = path.abspath(path.dirname(__file__))
        self.filepath_config_logging = path.join(self.app_dirpath, 'renderwatch/logging.yml')
        self.filepath_actions_schema = path.join(self.app_dirpath, 'renderwatch/actions.schema.yml')
        # In System OS Application Support Directory/renderwatch
        self.dirpath_user_config_dir = platformdirs.user_data_dir(appname='renderwatch', ensure_exists=True)
        self.dirpath_user_config_log_dir = platformdirs.user_data_dir(appname='renderwatch/logs', ensure_exists=True)
        self.filepath_user_config = path.join(self.dirpath_user_config_dir, 'config/config.yml')
        self.filepath_user_actions = path.join(self.dirpath_user_config_dir, 'config/actions.yml')
        # Import logging config
        with open(self.filepath_config_logging, 'r', encoding='utf-8') as f:
            log_config_yaml = yaml.safe_load(f)
            # TODO: improve this honestly
            log_config_yaml['handlers']['logfile']['filename'] = path.join(self.dirpath_user_config_log_dir, 'renderwatch.log')
            logging.config.dictConfig(log_config_yaml)

        self.event_internal = InternalEvents()
        self.event_resolve = ResolveEvents()
        self.event_user = UserEvents()

        self.resolve = False
        self.current_project = { }
        self.current_db = False

        self.render_jobs = {}
        self.render_jobs_first_run = True

        # Parse config
        with open(self.filepath_user_config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        self.config = config

        # Parse actions
        self.actions = []
        self._validated_user_steps = {}
        self._validate_user_actions()

    def _validate_user_actions(self):
        actions_schema = yamale.make_schema(self.filepath_actions_schema)
        actions_raw_text = open(self.filepath_user_actions, 'r', encoding='utf-8').read()
        actions_raw = yamale.make_data(content=actions_raw_text)
        try:
            yamale.validate(actions_schema, actions_raw)
            logger.debug('Actions validated OK 👍 File: %s', self.filepath_actions_schema)
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
        count_successful_user_actions = 0
        for index, definition in enumerate(actions):
            try:
                action = UserAction(
                    renderwatch = self,
                    index = index + 1, # order it appeared in user's actions.yml
                    enabled = definition['enabled'],
                    name = definition['name'],
                    steps = definition['steps'],
                    triggers = definition['triggered_by']
                )
                self.actions.append(action)
                count_successful_user_actions += 1
            except UserInvalidAction:
                logger.error(f"This action was invalid: index {index}: {definition['name']}")
        logger.debug(f"Parsed {count_successful_user_actions} user actions successfully.")

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
            logger.error('update_render_jobs(): No connection to Resolve available - quitting self. Launch Resolve and run again.')
            raise SystemExit
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

    def format_message_from_renderjob(
        self,
        text_to_format: str,
        job: RenderJob,
    ):
        output = False
        try:
            output = text_to_format.format(**job.__dict__)
        except KeyError as e:
            logger.error(f"format_message(): did not recognise this param: {e}. Check your actions.yml")
        return output

# Daemon
async def main():
    print('Welcome. Python:', sys.version, locale.getlocale())
    renderwatch = RenderWatch()
    run = True
    logger.debug('Connecting to Resolve for first time...')
    try:
        while run:
            await renderwatch.update_render_jobs()
            time.sleep(renderwatch.config['renderwatch_daemon']['API_poll_time'])
            # DEBUG:
            # renderwatch.event_resolve.render_job_started()
    except SystemExit:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.debug(e, exc_info=1)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
            
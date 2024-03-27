import datetime
import logging
import logging.config
import math

import dictdiffer
import humanize

logger = logging.getLogger(__name__)

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

        self.id = job_dump['JobId']
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
import datetime
import time
import sys

import dictdiffer
from pydavinci import davinci
import yaml


# Globals
RENDERWATCH_API_POLL_TIME = 2 

# Objects
class Action:
	def __init__(self, definition):
		if not definition.hasattr('name'):
			return None
		if not definition.hasattr('enabled'):
			if not definition.enabled:
				return False
		self.name = definition.name
		self.enabled = definition.enabled
		self.triggers = []
		for trigger in definition.trigger_when:
			self.triggers.append(trigger)

class RenderJob:
	def __init__(self, job_dump, render_status_info, time_collected, first_run=False):
		time_collected = datetime.datetime.now()
		jid = job_dump['JobId']
		self.id = jid
		self.history = {}
		self.first_run = first_run
		self.last_touched = False

		# Run first time
		self.update(job_dump, render_status_info, time_collected)

	def update(self, job_dump, render_status_info, time_collected):
		# Convert to integer for internal use
		timestamp = int(time_collected.timestamp())
		# Combine render_status into the job_dump, since it has unique k/vs
		job_dump.update(render_status_info)

		def _create_history_entry(job_dump):
			return {
				'id': job_dump['JobId'],
				'time': time_collected,
				'job': job_dump,
				# And some easier param names for the common stuff
				'name': job_dump['RenderJobName'],
				'target_directory': job_dump['TargetDir'],
				'timeline_name': job_dump['TimelineName'],
				# Render status
				'job_status': job_dump['JobStatus'],
				'job_completion_percent': job_dump['CompletionPercentage'],
			}
		# Mark that we checked this
		self.last_touched = timestamp
		# First record of this job
		if len(self.history) == 0:
			if self.first_run:
				event_render_job_new_firstrun(job_dump)
			else:
				event_render_job_new(job_dump)
			self.history[timestamp] = _create_history_entry(job_dump)
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
				difference = dictdiffer.diff(job_dump, latest_job)
				for d in difference:
					print(d)
				event_render_job_change(job_dump)
				# Save a new history entry
				self.history[timestamp] = _create_history_entry(job_dump)
				return True

	def status(self):
		latest = max(self.history)
		return self.history[latest]


class Daemon:
	
	def __init__(self):
		self.render_jobs = {}
		self.render_jobs_first_run = True

		# Parse config
		stream = open('config.yml', 'r')
		config = yaml.safe_load(stream)

		# Open actions
		stream = open('actions.yml', 'r')
		actions = yaml.safe_load(stream)

	def _check_api(self):
		try:
			davinci
		except:
			log("Error: pydavinci wasn't available. Is it installed correctly via pip?")
		Resolve = davinci.Resolve()
		if Resolve._obj:
			return Resolve
		else:
			log("Error: pydavinci could not connect to Resolve API. Is Resolve running?")
			return False

	def update_render_jobs(self):
		Resolve = self._check_api()
		# Mark the jobs with time that this call was made
		time_collected = datetime.datetime.now()
		timestamp = int(time_collected.timestamp())
		# Save the jobs as an ongoing database
		for job_dump in Resolve.project.render_jobs:
			if not 'JobId' in job_dump:
				continue
			# Store them by ID
			jid = job_dump['JobId']
			# Lookup render status
			render_status_info = Resolve.project.render_status(jid)
			# Create a new instance so we can track history of job status by time
			if not jid in self.render_jobs:
				if self.render_jobs_first_run:
					# To print the first jobs differently and not run any accidental notifs for '!!new jobs'
					# that are not new and were just there before daemon started.
					self.render_jobs[jid] = RenderJob(job_dump, render_status_info, time_collected, first_run=True)
				else:
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
				event_render_job_removed(job)
				# Mark for deletion
				delete_these_jobs.append(jid)
		# Apply deletion from our records
		for job in delete_these_jobs:
			self.render_jobs.pop(job)

def event_render_job_new(job_dump):
	log('Event - This render job was added:', job_dump['JobId'])

def event_render_job_new_firstrun(job_dump):
	log('Event - This render job is present in the Render Queue:', job_dump['JobId'])

def event_render_job_change(job_dump):
	log('Event - This job changed in some way:', job_dump['JobId'])

def event_render_job_removed(job):
	log('Event - This job was removed:', job.id)


# Utilities

def log(text, *args):
	print('daemon.py:', datetime.datetime.now().strftime('%H:%M:%S'), text, *args)



if __name__ == '__main__':
	log('Welcome.')
	log('Python:', sys.version)
	log('Resolve API being polled every (seconds):', RENDERWATCH_API_POLL_TIME)
	daemon = Daemon()

	while True:
		if daemon._check_api():
			daemon.update_render_jobs()
			for job_id, job in daemon.render_jobs.items():
				# Print latest status about each job - rn=right now
				job_rn = job.status()
				# print( f"{job_rn['name']} - {job_rn['timeline_name']} - {job_rn['job_status']}" )
		time.sleep(RENDERWATCH_API_POLL_TIME)
			


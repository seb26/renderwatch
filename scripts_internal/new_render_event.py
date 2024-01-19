import datetime
import sys
import pkgutil
from pydavinci import davinci

def log(text, *args):
	print(datetime.datetime.now(), 'new_render_event.py:', text, *args)

log('Running.')
log(sys.version)

"""
This is an 'internal' script, which is meant to be executed by Resolve
with an API context already under the object `resolve`.
"""
try:
	resolve
except:
	quit('Quit. No resolve object. ')


log(resolve)
log('Using pydavinci now')
Resolve = davinci.Resolve()
log(Resolve)

project_manager = Resolve.project_manager
current_project = Resolve.project
print(current_project)

# JOBS
print('current project:', current_project.name)
print('render jobs:', current_project.render_jobs)
jobs = current_project.render_jobs

for job in jobs:
	print(current_project.render_status(job['JobId']))
log('End.')



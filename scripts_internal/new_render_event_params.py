import datetime
import sys
import pkgutil
# from pydavinci import davinci

def log(text, *args):
	print(datetime.datetime.now(), 'new_render_event_params.py:', text, *args)

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

log('Job, status, error.')

print(job)
print(status)
print(error)
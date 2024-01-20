from pydavinci import davinci
import datetime
import time

def log(text, *args):
	print(datetime.datetime.now().strftime('%H:%M:%S.%f'), text, *args)


resolve = davinci.Resolve()

while True:
	project = resolve.project
	for job in project.render_jobs:
		jid = job['JobId']
		log(job['RenderJobName'], resolve.project.render_status(jid))
	time.sleep(2)

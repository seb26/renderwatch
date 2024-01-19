from pydavinci import davinci
import datetime
import time

def log(text, *args):
	print(datetime.datetime.now().strftime('%H:%M:%S.%f'), text, *args)


resolve = davinci.Resolve()

while True:
	log(resolve.project.render_status("bd390c32-7a4e-4ae3-b5d8-0eacfb56728d"))
	time.sleep(0.5)

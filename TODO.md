# TODO

* Make it clear to user that this daemon only works for the currently opened Project
	* Perhaps a way to nominate other projects for Daemon to watch?


x Add event for new job
x Add event for deleted job

* Create list of events total that will be made
	render_job_new
	render_job_complete
	render_job_rendering
	render_job_cancelled
	render_job_status_change_other
	render_job_removed
	 

* Events need to parse the result of dictdiffer into a practical result - aka "keyvalue change for JobStatus from Rendering to Complete" needs to be interpreted in words as 'Job Completed'
	* Also determine an Elapsed time - take job completed timestamp and minus from earliest(job history) timestamp

* Remove logging for "Updating..." every 2 seconds - eventually only log for Errors and Events that the user specifies, and maybe a Verbose mode

* Convert Time Interval for polling the Resolve API, into a parameter with a reasonable default

* A way to provide the filepaths
	* Test if output file ends with " and more" - that is Resolve API's wonderful way of providing you only the first clip in a job of Individual clips that clearly has way more clips than that
	* If a single clip, provided completed filepath
	* Otherwise perhaps display to user only the Output Folder

* Respond to events

	* Notification functions:
		* Email
		* Twitter
		* Logging in the Daemon


	* Trigger a shell command or script
		* Quickest way to allow a file transfer (e.g. Rsync), and so that it takes place as a separate process where user can control it independent of the daemon
		* And without having a GUI that I have to manage






## R&D
x Do a test to see if you can poll JobStatus every 0.5sec - how frequently does the API give you a CompletionPercentage?
	* Done, it seems to only report 0/25/50/75/100% intervals and the time remaining in miliseconds is a big whole number rounded to hundreds

* Test what jobs are like when they are QUEUED

* Test what jobs are like when they are REMOTE RENDERING

* Maybe the internal script 'trigger_render_event' shouldn't be used for End.
	* There's no way to distinguish if End or Start was used by the user.
	* If the user uses End, all it can do is just poll and see Complete render jobs. How do you tell if it completed Just Now, or completed hours ago?
	* If user uses Start, it is more useful. It can provide an event that fires at the exact moment of Start (more accurate time) and since there is only one job that is 'Rendering' at the time of firing, then it is definitive which job was associated with the trigger


	* Internal script should also include an internal keyvalue to suggest that its job dump came from a Render job, so that could be filtered at some point from the majority of Polled job dumps 
		* For example, to provide a more accurate completion time
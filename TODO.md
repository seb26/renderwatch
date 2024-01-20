# TODO

* Make it clear to user that this daemon only works for the currently opened Project
	* Perhaps a way to nominate other projects for Daemon to watch?

* Events to add
	* Loss of Resolve API -- may indicate a program crash or program closed during operation

* Implement Actions


* Events need to interpret the result of dictdiffer into a practical result - aka "keyvalue change for JobStatus from Rendering to Complete" needs to be interpreted in words as 'Job Completed'
	* Also determine an Elapsed time - take job completed timestamp and minus from earliest(job history) timestamp

* Convert Time Interval for polling the Resolve API, into a parameter with a reasonable default

* Change RenderJob update() to be Asynchronous
	* This will help a follow-up API call to be made, if we get surprising info from an API call and need to make another one
	* One important reason - Allow a follow up call for Render Statuses, if one of the Renders hits 'Completed' - we will then learn immediately if another job was queued straight after

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



* FAILED jobs
	* Workaround for issue where Failed Renders are not visible to API until OK dialog is dismissed
	* Consider using Osascript to send Fn+Return keystroke to 'OK'
	* Consider watching ~/App Support/BMD/Resolve/davinci_resolve.log for IO errors
		* Will this catch all types of errors?
		* Maybe it's enough to focus the screen and therefore force the API to respond


## R&D
x Do a test to see if you can poll JobStatus every 0.5sec - how frequently does the API give you a CompletionPercentage?
	* Done, it seems to only report 0/25/50/75/100% intervals and the time remaining in miliseconds is a big whole number rounded to hundreds

* Test what jobs are like when they are QUEUED
	* 19/01/2024 - There's nothing different about a Job that is Queued or not. They are both "Ready"
	* For 2 or more jobs, there may be a slight gap in time between the first job finishing as 'Complete' and the next one 'Rendering'
	* This means it may be helpful to do another poll immediately after receiving news that a job has Completed, in order to be more responsive about subsequent jobs

* Test what jobs are like when they are REMOTE RENDERING

* Test what jobs are like when they FAIL

	* 19/01/2024 - When a job fails, Resolve shows the UI a Dialog box with error message. API continues to report 'Rendering' aka is UNAWARE there was a failure. Python Console is the same. Once user presses OK on the Failure dialog box, then the API reports Failure and the error message and Console too.
	* This is a problem - means user interaction or keyboard strokes are required, no programmatic way to identify a Failed render.
	* Recommend reporting bug to Blackmagic.

* Maybe the internal script 'trigger_render_event' shouldn't be used for End.
	* There's no way to distinguish if End or Start was used by the user.
	* If the user uses End, all it can do is just poll and see Complete render jobs. How do you tell if it completed Just Now, or completed hours ago?
	* If user uses Start, it is more useful. It can provide an event that fires at the exact moment of Start (more accurate time) and since there is only one job that is 'Rendering' at the time of firing, then it is definitive which job was associated with the trigger


	* Internal script should also include an internal keyvalue to suggest that its job dump came from a Render job, so that could be filtered at some point from the majority of Polled job dumps 
		* For example, to provide a more accurate completion time

	* 19/01/2024 - FOUND OUT THERE are 3 variables accessible to a triggered Start/End script:
		job - string, the job ID
		status - string, "RenderCompleted", "RenderStarted", "RenderFailed"
		error - string, empty if no error, otherwise error message text
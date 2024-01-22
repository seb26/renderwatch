# TODO

* Make it clear to user that this daemon only works for the currently opened Project
	* Perhaps a way to nominate other projects for Daemon to watch?

* Events to add
	* Loss of Resolve API -- may indicate a program crash or program closed during operation

    * Consider if Events implementation needs to be Asynchronous

    * Add an Output Filepath AND Output Directory as a quick param for Actions to use in their messaging
    	* Needs to handle Single clip where there is a Single file path, but also the ` and more` suffix that Resolve uses to indicate multiple clips


x Implement Actions backend

* Allow Actions file to be modified - watch for OS filesystem changes and reload

* Implement these Action Steps
    * Telegram
    * Email
    * Trigger a shell command or script
    	* Quickest way to allow a file transfer (e.g. Rsync), and so that it takes place as a separate process where user can control it independent of the daemon
		* And without having a GUI that I have to manage

    * Need some default messaging or statuses - User will want to customise but also they won't want to for Render Status Change! Have a default string that contains exactly what happened in nice words (similar to CLI logging) and put that as a template like `{status_change}`

* Remove DIY logging and implement Python Logging library

* Implement config
    * Should have a Yamale schema but make it quite flexible at first
    * Add option for Time Interval for polling the Resolve API

* Feature idea - Also determine an Elapsed time? - take job completed timestamp and minus from earliest(job history) timestamp

* Change RenderJob update() to be Asynchronous
	* This will help a follow-up API call to be made, if we get surprising info from an API call and need to make another one
	* One important reason - Allow a follow up call for Render Statuses, if one of the Renders hits 'Completed' - we will then learn immediately if another job was queued straight after

* Perform another API poll after receiving news that a job has completed
    * Might require Asynchronicity since that request for another API poll will come from inside update()

* FAILED jobs
    * Current decision:
    	* In default program installation, Failed event notifications are available but are not instantaneous, a user must interact with the screen and then the notification fires
        * Cause: Issue in DVR where Failed Renders are not visible to API or Console until OK dialog is dismissed
        * With an Optional component, Failed Event notification is available semi-instantaneously, but user must enable a program to have access to System Events

    * Optional component that works around this Issue:
    	* Consider watching ~/App Support/BMD/Resolve/davinci_resolve.log for IO errors
    		* Will this catch all types of errors?
    		* Maybe it's enough to focus the screen and therefore force the API to respond
            * Better than sending Keystrokes to a screen blindly at some interval
    	* Consider using Osascript to send Fn+Return keystroke to 'OK'
        	* Be smart - after that keystroke sent, watch for an Failed event and if there is none in a reasonable time period, be cautious about how many further keystrokes you send 


## R&D within DaVinci Resolve
x Do a test to see if you can poll JobStatus every 0.5sec - how frequently does the API give you a CompletionPercentage?
	* Done, it seems to only report 0/25/50/75/100% intervals and the time remaining in miliseconds is a big whole number rounded to hundreds

* Test what jobs are like when they are QUEUED
	* 19/01/2024 - There's nothing different about a Job that is Queued or not. They are both "Ready"
	* For 2 or more jobs, there may be a slight gap in time between the first job finishing as 'Complete' and the next one 'Rendering'
	* This means it may be helpful to do another poll immediately after receiving news that a job has Completed, in order to be more responsive about subsequent jobs

* Test what jobs are like when they are REMOTE RENDERING

* Test what jobs are like when they have ADDITIONAL VIDEO OUTPUTS (aka main render is ProRes and additional output of H264)
    * You can have multiple!!!

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
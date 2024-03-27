## renderwatch

A library for connecting to DaVinci Resolve and accessing Render Job details and firing events in response to job changes.

`renderwatch_daemon.py` monitors job changes and can fire events like send a Telegram message or run a shell command.

### Usage

1. Download binary
2. Launch DaVinci Resolve Studio. In Preferences > System, ensure "External scripting" is set to Local
3. Run `renderwatch_daemon` once - to generate a config file and actions file
4. Edit event actions at `~/Library/Application Support/renderwatch/actions.yml` and config at `config.yml`
5. Run `renderwatch_daemon` again

### Actions

~/Library/Application Support/renderwatch/config/actions.yml

```yaml
actions:
  - name: Job starts
    enabled: true
    triggered_by:
      - render_job_started
      - render_job_progress_initial_update
    steps:
      - telegram:
          action: send_message
          chat_id: -000000000 # Fill this in
          message: '🔂 {name}: {timeline_name} - {status} @ {timestamp_short}{line_time_remaining}'

  - name: Job finishes OK
    enabled: true
    triggered_by:
      - render_job_completed
    steps:
      - telegram:
          action: send_message
          chat_id: 
          message: "✅ {name}: {timeline_name} - {status} @ {timestamp_short} {line_time_elapsed} {line_average_fps}"

  - name: Job fails
    enabled: true
    triggered_by:
      - render_job_failed
      - render_job_cancelled
    steps:
      - telegram:
          action: send_message
          chat_id: 
          message: "⚠️ {name}: {timeline_name} - {status} @ {timestamp_short} {line_completion_percent}"
```

### Config

~/Library/Application Support/renderwatch/config/config.yml

```yaml
renderwatch:
  steps:
    telegram:
      token_plaintext: 
      token_filepath: 
      token_env_var: YOUR_ENV_VAR_NAME
```

### TODO

Also current issues are described here:

[TODO.md](TODO.md)
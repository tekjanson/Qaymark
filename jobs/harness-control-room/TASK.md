# Job: Harness control room

Build a browser-based control room for Qaymark that lets a human watch and
steer the harness.

## What to do

Implement a small state engine in `control_room.py` and a static browser UI in
`index.html`, `app.js`, and `styles.css`.

Store load-bearing work in a persistent workspace or an existing git repo; do
not rely on `/tmp` for anything that must survive cleanup.

The UI should show:

- a chat pane for operator messages
- a project list for the harness jobs
- a queue/orchestration panel with pause and resume controls
- a live status area for the current run

Every feature needs a corresponding UI interaction so the operator can do the
same thing from the browser that the harness can do programmatically.

## Acceptance

Validate with:

```bash
python3 -m unittest test_control_room && node --check app.js
```

## Style constraints

Keep lines at or under 100 characters, keep functions small, avoid placeholder
comments, and do not use `eval`.

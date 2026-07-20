# Jobs

A **job** is a fixed spec the Qaymark factory must satisfy: a task description
plus a `seed/` directory of files (typically acceptance tests) that are planted
into every worker's workspace and **protected** — the model cannot edit them.

A job passes only when the generated code makes the seeded tests pass *and*
clears the strict hygiene gate.

## Layout

```
jobs/<name>/
  TASK.md        # the task/spec (passed to the harness as --task)
  seed/          # files planted into the workspace (protected acceptance tests)
  starter/       # editable scaffold planted into the workspace (the model fills it)
  run.sh         # convenience runner
  example/       # a solution the factory produced (for reference)
```

`seed/` files are protected (the model cannot edit them). `starter/` files are a
head start the model completes. Generated code is auto-formatted with `black`
(if on PATH) before the strict hygiene gate, so the model only has to get the
logic right.

## Tetris

Build a headless Tetris core that passes `seed/test_tetris.py`:

```bash
jobs/tetris/run.sh /tmp/qaymark-tetris
# or tune it:
WORKERS=1 HARNESS_MAX_ATTEMPTS=8 OLLAMA_MODEL=qwen2.5-coder:7b \
  jobs/tetris/run.sh /tmp/qaymark-tetris
```

The winning `tetris.py` lands in the workspace (or `<workspace>/result` for a
fleet). `example/tetris.py` is a solution the factory generated — it passes all
16 acceptance tests and the strict hygiene gate.

## Playable web Tetris

Build a browser-playable Tetris that passes `seed/test_webtetris.py` and ships
the `index.html` / `app.js` / `styles.css` UI alongside `webtetris.py`:

```bash
jobs/tetris-web/run.sh /tmp/qaymark-tetris-web
# or tune it:
WORKERS=1 HARNESS_MAX_ATTEMPTS=8 OLLAMA_MODEL=qwen2.5-coder:7b \
  jobs/tetris-web/run.sh /tmp/qaymark-tetris-web
```

The winning workspace is static-site ready; open it from a local web server to
play in the browser.

## Harness control room

Build a browser-based control room for the harness itself: chat, project list,
queue management, and pause/resume orchestration controls.

```bash
jobs/harness-control-room/run.sh
# or tune it:
WORKERS=1 HARNESS_MAX_ATTEMPTS=8 OLLAMA_MODEL=qwen2.5-coder:7b \
  jobs/harness-control-room/run.sh "$HOME/.local/state/qaymark/control-room"
```

The goal is a live operator surface for steering multiple harness projects from
one place, with durable work kept out of `/tmp`.

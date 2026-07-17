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
  run.sh         # convenience runner (fleet)
```

## Tetris

Build a headless Tetris core that passes `seed/test_tetris.py`:

```bash
jobs/tetris/run.sh /tmp/qaymark-tetris
# or tune the fleet:
WORKERS=4 HARNESS_MAX_ATTEMPTS=8 OLLAMA_MODEL=qwen2.5-coder:7b \
  jobs/tetris/run.sh /tmp/qaymark-tetris
```

The winning workspace is copied to `<workspace>/result`.

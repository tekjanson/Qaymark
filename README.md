# Qaymark

**Qaymark** is a guardrailed, fully local AI **code-generation factory**. It
wraps a single Ollama code-generation call in a programmatic loop that forces
the output to be clean and structurally consistent before it is accepted.

[Waymark](https://github.com/tekjanson/Waymark) is the intended **visual
frontend** — you can drive the factory through its agentic visibility tools —
but the Qaymark **CLI is fully usable on its own**.

Two layers:

1. **Runtime** — [Ollama](https://ollama.com) for the model and
   [Open WebUI](https://github.com/open-webui/open-webui) for a browser chat,
   both in Docker. Runs offline, costs nothing.
2. **Harness** — a programmatic loop (`qaymark/`) that wraps a single Ollama
   code-generation call and gates the result on two real tools:
   - **[slop-be-gone](https://github.com/spamApply1/slop-be-gone)** (`sbg`) —
     the hygiene gate. Generated code must pass the strict rule set in
     `sbg_manifest.json` (no placeholders, no marker spam, no debug artifacts,
     no secrets, small/flat/few-arg functions, and more).
   - **[idud](https://github.com/tekjanson/idud)** — the reference map. Builds a
     synthetic understanding artifact (a dependency graph / "bridges") so the
     model knows what already exists and what to touch.

   Each attempt is a **single one-shot generation**. There are no chat turns:
   the harness itself does all the tool work (applying edits, running
   validation, running the gates) and folds the results into targeted feedback
   for the next one-shot.

The same hygiene gate runs as a **git pre-commit hook and in CI**, so the rules
apply to hand-written code too — see [Guardrails](#guardrails).

## Requirements

- Docker + Docker Compose v2
- Python 3.10+
- `git`, and (optional) `cargo` for the idud reference bridge
- A running Ollama with a coding model pulled (the runtime below does this)

## Quick start

Start the runtime and pull the default model:

```bash
make up
```

- Open WebUI: <http://localhost:8095>  (moved off `3000` to avoid clashing with
  dev servers such as Waymark)
- Ollama API: <http://localhost:11434>
- Control plane: `make dashboard ROOT=/tmp/qaymark-dashboard` with
  `DASHBOARD_USER` / `DASHBOARD_PASSWORD`

Run the guardrailed harness against a workspace:

```bash
make harness TASK="Create a Python module that adds two numbers with a CLI" \
             WORKSPACE=/tmp/adder-demo
```

Or install the CLI and run it from anywhere:

```bash
pip install -e .
qaymark \
  --task "Create a Python module that adds two numbers with a CLI" \
  --workspace /tmp/adder-demo \
  --validation-command "python3 -m compileall -q ."
```

The `python3 scripts/code_harness.py ...` invocation still works too.

## How the harness loop works

For each attempt (default 3):

1. **Snapshot** the workspace and build a one-shot prompt (task + validation
   command + snapshot + previous feedback).
2. **Generate** a single JSON action payload from Ollama (`/api/chat`).
3. **Apply** the file operations, constrained to the workspace (absolute paths
   and `..` traversal are rejected; `run_command` is disabled unless you opt in
   with `--allow-commands`).
4. **Validate** by running the validation command (must exit 0).
5. **Gate on hygiene** with the real `sbg` engine and `sbg_manifest.json`.
6. **Build the idud reference** for the workspace (graph nodes/edges + brief).
7. If validation and hygiene both pass, **stop and succeed**. Otherwise fuse the
   validation output, hygiene violations, and idud summary into **targeted
   feedback** and run another one-shot.

Per-attempt artifacts are written under `<workspace>/.harness/`.

The `sbg` and `idud` tools are cloned (and idud built) once into a cache
directory (`~/.cache/local-coding-harness` by default) and reused. If a tool
cannot be provisioned, the harness degrades gracefully: a minimal built-in
hygiene scanner stands in for `sbg`, and the idud step is skipped.

## Around-the-clock supervisor (the perfection loop)

`make harness` builds once and exits. `make supervise` keeps the factory alive:
after the first green build it **watches for human feedback** and rebuilds
automatically whenever you leave a note in the control plane.

```bash
make supervise TASK="$(cat jobs/tetris-web/TASK.md)" WORKSPACE=/tmp/factory/tetris
```

1. It builds once (same guardrailed loop) and lands in the `watching` phase.
2. You open the dashboard, and in the **Feedback** panel you type what you don't
   like ("this sucks, make the board bigger"). You never have to touch the code
   or the terminal.
3. The supervisor folds your note into the next one-shot and rebuilds. The
   rebuild is **snapshotted first and rolled back if it fails** the tests or
   hygiene gate, so the workspace never regresses to a broken state.
4. It returns to `watching` for your next note — around the clock.

Feedback is stored per workspace in `<workspace>/.harness/feedback.txt`; the
harness reads it on every attempt, so it also works as plain-text drop-in.

## Control plane (single sign-in)

One login gives you visibility over every workspace under a root directory —
phases, attempts, validation, hygiene, and the feedback channel:

```bash
export DASHBOARD_USER=admin DASHBOARD_PASSWORD='choose-a-password'
make dashboard ROOT=/tmp/factory PORT=8765
# open http://127.0.0.1:8765 and sign in
```

The dashboard discovers any workspace with a `.harness/status.json` beneath
`ROOT`, shows a global overview (total / running / passed / failed), and lets
you submit feedback that drives the supervisor's next rebuild.

## The hygiene manifest

`sbg_manifest.json` enables every slop-be-gone rule at **error** severity with
tightened thresholds — the "fractal consistency" policy:

- No placeholder comments, deferred-work marker spam, empty files, or oversized files
- Lines ≤ 100 chars; a single final newline; no trailing whitespace
- No merge markers, committed secrets, or leftover debug artifacts
- Python AST rigor: no bare/broad `except`, no mutable defaults, no `eval`/`exec`
- Small, flat functions: ≤ 45 lines, ≤ 5 arguments, ≤ 4 levels of nesting

Validate it against the real engine:

```bash
python3 -m sbg.cli validate . --manifest ./sbg_manifest.json
```

## Commands

```bash
make up                 # start the stack + pull the model
make down               # stop the stack
make chat PROMPT="..."  # one-off prompt
make harness TASK="..." WORKSPACE=/dir
make test               # run the harness unit tests
make clean              # remove the tool cache
```

## Configuration

Copy the example env and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_MODEL` | `qwen2.5-coder:3b` | Model to pull/use |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `WEBUI_PORT` | `8095` | Open WebUI host port |
| `OLLAMA_ORIGINS` | `*` | Browser origins allowed to call Ollama (for Waymark) |
| `WEBUI_AUTH` | `False` | WebUI auth (disable only on a fresh DB) |
| `RESET_WEBUI_DATA` | `0` | Wipe the WebUI DB on bootstrap (destructive) |
| `HARNESS_MAX_ATTEMPTS` | `3` | One-shot attempts per run |
| `HARNESS_ALLOW_COMMANDS` | `0` | Permit model `run_command` operations |
| `HARNESS_USE_IDUD` | `1` | Build/use the idud reference bridge |
| `DASHBOARD_USER` | `admin` | Sign-in username for the control plane |
| `DASHBOARD_PASSWORD` | `qaymark` | Sign-in password for the control plane |

> Disabling `WEBUI_AUTH` only works on a fresh Open WebUI database. If you see
> "You can't turn off authentication because there are existing users", run once
> with `RESET_WEBUI_DATA=1 ./scripts/bootstrap.sh`.

## Guardrails

The hygiene gate is not optional. It runs in three places so neither the model
nor a human can quietly ship slop:

- **Harness** — every generated attempt must pass before it is accepted.
- **Pre-commit hook** — `.githooks/pre-commit` runs the strict gate on staged
  files. Enable it once per clone:

  ```bash
  git config core.hooksPath .githooks
  ```

- **CI** — `.github/workflows/ci.yml` runs the same gate plus the unit tests on
  every push and pull request.

The hook and workflow are **version-controlled**, so any change to the guardrails
is visible in the diff and reviewable. Lock `main` with branch protection
(require the CI check, forbid force-pushes) to make the gate effectively
unbypassable — do not commit with `--no-verify`.

The gate itself is `scripts/hygiene_gate.py`; it fails closed if `sbg` cannot be
provisioned.

## Tests

```bash
make test
```

The suite runs without Ollama: the loop test mocks the model and exercises the
full apply → validate → hygiene-gate → feedback pipeline. When `sbg` is
importable, the manifest is additionally validated against the real engine.

## Layout

```
docker-compose.yml     Ollama + Open WebUI stack
sbg_manifest.json      Strict slop-be-gone hygiene policy
pyproject.toml         Installable `qaymark` CLI
Makefile               One-command entry points
qaymark/               The guardrailed harness package
  config.py            Settings and path resolution
  ollama_client.py     /api/chat client
  workspace.py         Snapshotting + .sbgignore
  operations.py        Safe file-operation application
  references.py        Clone/build the sbg + idud tools
  hygiene.py           slop-be-gone gate (+ degraded fallback)
  idud_bridge.py       idud understanding artifact bridge
  prompt.py            Prompt + feedback synthesis
  loop.py              Orchestration
  cli.py               Command-line entry point
scripts/
  bootstrap.sh         Start the stack + pull the model
  chat.sh              One-off prompt helper
  hygiene_gate.py      Strict gate used by the hook + CI
  code_harness.py      Backward-compatible harness entry point
.githooks/pre-commit   Version-controlled hygiene hook
.github/workflows/     CI enforcement
tests/                 Unit tests (stdlib unittest)
```

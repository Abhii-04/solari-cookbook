---
name: repo_startup_discovery
description: Find and run the correct startup or smoke-test command for an unfamiliar cloned repository inside a sandbox. Use this whenever a repo setup flow cannot detect a smoke command, needs to infer how to run a GitHub repo from README files, manifests, and folder structure, or needs to install missing language runtimes before installing repo packages. Do not use repo-authored tests as part of setup validation.
---

# Repo Startup Discovery

Your job is to discover the safest command that proves a cloned repo can run inside the sandbox. Do not guess from one filename alone. Build evidence from the README, folder structure, and manifests. If the repo's language runtime or package manager is missing, prefer bootstrapping the missing runtime/tool in the sandbox before giving up, then retry dependency installation and smoke discovery.

## Required Result

Return a concise machine-readable summary:

```text
REPO_STARTUP_DISCOVERY_BEGIN
DOCS_READ
- <README/docs files read>
STRUCTURE_SIGNALS
- <important files/folders found>
RUNTIME_BOOTSTRAP
- <language runtimes/package managers required and whether they were found, installed, or unavailable>
SMOKE_COMMAND_FOUND <command>
STARTUP_COMMAND_FOUND <command>
COMMAND_EVIDENCE
- <why these commands were chosen>
COMMAND_RESULT
- <exit code and short result>
REPO_STARTUP_DISCOVERY_END
```

If a command is not found, use:

```text
NO_SMOKE_COMMAND_FOUND <reason>
NO_STARTUP_COMMAND_FOUND <reason>
```

## Discovery Workflow

Follow this order:

1. Read README and project docs.
2. Inspect the shallow folder structure.
3. Inspect manifests such as `pyproject.toml`, `package.json`, `go.mod`, or `Cargo.toml`.
4. Identify required language runtimes and package managers from manifests.
5. Bootstrap missing runtimes/tools in the sandbox when a safe installer is available.
6. Install dependencies from the repo's manifests.
7. Identify the safest smoke/startup command.
8. Run startup commands with a timeout.

Prefer explicit README instructions over inferred commands, but verify the files/scripts named in the README actually exist.

## Read The Docs First

Read likely root docs:

```text
README.md
README.rst
README.txt
docs/README.md
CONTRIBUTING.md
DEVELOPMENT.md
INSTALL.md
```

Search those files for:

```text
quickstart
install
run
start
usage
development
uv
poetry
npm
pnpm
yarn
bun
cargo
go run
docker compose
```

If docs contain both local development and deployment commands, choose the local development command. Do not choose deploy, publish, release, cloud, migration, production, or repo-authored test commands for a sandbox smoke test.

## Inspect Structure

Use shallow structure signals:

```bash
pwd
rg --files | sed -n '1,200p'
```

Look for:

```text
main.py
app.py
server.py
manage.py
src/
package.json
pyproject.toml
uv.lock
requirements.txt
Makefile
go.mod
Cargo.toml
docker-compose.yml
compose.yml
```

Use structure to validate the command. For example, only report `uv run python main.py` if `main.py` exists.

## Python Repos

Inspect:

```text
pyproject.toml
uv.lock
poetry.lock
requirements.txt
setup.py
setup.cfg
```

Smoke/startup priority:

```text
uv run <console-script from pyproject.toml>
uv run python main.py
uv run python app.py
uv run python -m <package>
python main.py
python app.py
python -m <package>
```

In `pyproject.toml`, inspect `[project.scripts]`, `[project.gui-scripts]`, and `[tool.poetry.scripts]`.

If `uv.lock` exists, prefer `uv run ...` commands.

If Python is missing in the sandbox, install `python3`, `python3-pip`, and `python3-venv` with the sandbox's OS package manager when available, then install `uv`, `poetry`, or `pipenv` as needed. If Python cannot be safely installed, report `MISSING_TOOL python3`.

## Node Repos

Inspect `package.json` scripts and lockfiles.

Pick package manager by lockfile:

```text
pnpm-lock.yaml -> pnpm
yarn.lock -> yarn
bun.lock or bun.lockb -> bun
package-lock.json -> npm
```

Smoke/startup priority:

```text
npm run dev
npm start
pnpm dev
pnpm start
yarn dev
yarn start
bun run dev
bun start
```

Only report a script if it exists in `package.json`.

If Node or npm is missing in the sandbox, install `nodejs` and `npm` with the sandbox's OS package manager when available, then retry the package-manager install. For `pnpm` and `yarn`, try Corepack first and fall back to `npm install -g` only after npm is available. If a Bun lockfile is present and Bun cannot be safely installed, report `MISSING_TOOL bun` instead of switching package managers.

## Go And Rust Repos

For Go:

```text
SMOKE_COMMAND_FOUND timeout 20s go run .
```

If the repo uses `cmd/<name>`, prefer:

```text
SMOKE_COMMAND_FOUND timeout 20s go run ./cmd/<name>
```

For Rust:

```text
SMOKE_COMMAND_FOUND timeout 20s cargo run
```

If Go or Rust is missing in the sandbox, install `golang-go` or `cargo` with the sandbox's OS package manager when available before running `go mod download`, `go run`, `cargo fetch`, or `cargo run`.

## Makefile

If a `Makefile` exists, inspect targets. Safe targets include:

```text
smoke
run
dev
start
```

Unsafe targets include:

```text
deploy
publish
release
destroy
reset-db
clean-db
migrate-prod
```

Do not run unsafe targets.

## Safety Rules

Reject commands that:

- deploy, publish, release, or upload
- require cloud credentials or account login
- modify production databases
- reset, wipe, or destroy data
- pipe remote scripts into a shell, such as `curl ... | sh`
- need secrets from `.env`, private keys, or tokens
- run privileged containers

If only unsafe commands exist, report `NO_SMOKE_COMMAND_FOUND` and explain why.

## Running Commands

Do not run repo-authored tests as part of setup validation.

Use a timeout for anything that may start a server:

```bash
timeout 20s uv run python main.py
timeout 20s python main.py
timeout 20s npm start
timeout 20s npm run dev
timeout 20s cargo run
timeout 20s go run .
```

A timeout can still be a successful smoke result if logs show the app started normally and there was no traceback, fatal error, missing dependency, or crash.

## Selection Rules

When multiple commands are possible:

1. Prefer README-documented commands.
2. Prefer manifest scripts over raw inferred commands.
3. Prefer root-level entrypoints over deep guessed files.
4. Prefer commands that require no secrets, databases, browsers, or external accounts.
5. Prefer minimal smoke verification over full production launch.

If evidence conflicts, choose the safest command and explain the conflict.

## Examples

Python repo with `pyproject.toml`, `uv.lock`, and `main.py`:

```text
SMOKE_COMMAND_FOUND timeout 20s uv run python main.py
STARTUP_COMMAND_FOUND timeout 20s uv run python main.py
```

Node repo with `package.json` and `package-lock.json`:

```text
SMOKE_COMMAND_FOUND timeout 20s npm start
STARTUP_COMMAND_FOUND timeout 20s npm start
```

Repo where README only documents deployment:

```text
NO_SMOKE_COMMAND_FOUND README only documents deployment commands, which are unsafe for sandbox smoke verification.
```

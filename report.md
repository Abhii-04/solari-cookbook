# GitReady Project Report

## Current Snapshot

GitReady is a local Python CLI agent built with LangGraph. It routes user input between:

- a general assistant workflow for reasoning, local shell work, and direct Solari sandbox tasks
- a repository setup workflow that verifies a GitHub repository in Solari before cloning and installing it beside this project

The project still has some ULTRON naming inside prompts and user-facing text. The root README now calls the project GitReady, while internal package metadata still uses `name = "ultron"` in `pyproject.toml`.

## Runtime Requirements

- Python 3.11 or newer
- `uv` for dependency sync and local execution
- `DEEPSEEK_API_KEY` for the LangChain/OpenAI-compatible DeepSeek model
- `SOLARI_API_KEY` for sandbox creation and execution
- Optional Socket credentials through one of:
  - `SOCKET_API_TOKEN`
  - `SOCKET_API_KEY`
  - `SOCKET_CLI_API_TOKEN`
  - `SOCKET_CLI_API_KEY`
  - `SOCKET_SECURITY_API_TOKEN`
  - `SOCKET_SECURITY_API_KEY`

The application loads `.env` with `python-dotenv` in the main agent, assistant, repo setup workflow, and Solari wrapper.

## Installed Dependencies

The root `pyproject.toml` defines the package as Python-only and requires Python `>=3.11`.

Core runtime dependencies:

- `langgraph`, `langgraph-supervisor`
- `langchain`, `langchain-core`, `langchain-openai`, `langchain-mcp-adapters`
- `headroom-ai[langchain]`
- `solari-sandbox`
- `dotenv`
- `tavily`
- `mem0ai`
- Google OAuth / community LangChain packages

There are no configured project scripts, lint commands, or test commands in `pyproject.toml`.

## How To Run

Install dependencies:

```bash
uv sync
```

Start the CLI:

```bash
uv run python main.py
```

The current prompt is:

```text
Link:
```

Type `exit` or `quit` to stop the agent. `main.py` also joins immediately available stdin lines and keeps prompting with `... ` when the current input appears to end mid-thought, such as after `and`, `or`, `then`, `with`, `from`, `to`, a comma, or a trailing backslash.

## Verification Status

The README mentions:

```bash
uv run python -m unittest discover -s tests
```

However, this working tree currently has no `tests/` directory, and `git ls-files tests` returns no tracked test files. That means the documented unittest command is not currently runnable without restoring or adding tests.

A useful current smoke check is compiling the assembled sandbox script:

```bash
uv run python - <<'PY'
from src.nodes.script import sandbox_setup_script
script = sandbox_setup_script("https://github.com/example/demo.git", "demo")
compile(script, "<sandbox_setup_script>", "exec")
print("ok", len(script.splitlines()))
PY
```

## Project Layout

| Path | Current responsibility |
| --- | --- |
| `main.py` | CLI entrypoint and terminal input loop |
| `pyproject.toml` | Python package metadata and dependency list |
| `src/agent.py` | Top-level LangGraph coordinator and streaming runner |
| `src/config/state.py` | Shared graph state type and reducers |
| `src/subgraphs/assistant.py` | General assistant graph |
| `src/subgraphs/repo_setup.py` | Repository setup graph |
| `src/middlewares/dynamic_agent_selector.py` | First-pass route selection |
| `src/middlewares/context.py` | Repo setup context compaction and sandbox log capture |
| `src/middlewares/repo_setup_messages.py` | Repo setup tool payload and fallback extraction |
| `src/middlewares/repo_setup_progress.py` | Custom progress event emitter and heartbeat wrapper |
| `src/middlewares/repository_setup_logs.py` | Raw sandbox operations log extraction |
| `src/nodes/sandbox_repo_clone.py` | Solari setup tool that gates local clone/install |
| `src/nodes/local_setup.py` | Local clone, dependency install, repo profile, and tool installer helpers |
| `src/nodes/repo_setup_output.py` | Sandbox output parsing, progress events, and recovery questions |
| `src/nodes/repo_setup_summary.py` | Final setup report formatting |
| `src/nodes/script.py` | Sandbox setup script assembly from templates |
| `src/sandbox_tests/` | Template fragments executed inside Solari |
| `src/tools/SolariSandbox.py` | Solari SDK wrapper and LangChain tools |
| `src/tools/bash.py` | Local bash tool restricted to the project and sibling clone root |
| `src/tools/read_skill.py` | Reads repo-local skill instructions |
| `skills/repo_startup_discovery/SKILL.md` | Startup/smoke discovery instructions used by repo setup |
| `examples/` | Solari cookbook examples in Python and TypeScript |

## Top-Level Agent Flow

`main.py` creates an `Agent`, calls `setup()`, then repeatedly sends user input to `Agent.run_superstep()`.

`src/agent.py` builds this top-level graph:

```text
START
  -> router
  -> assistant | repo_setup | orchestrator
  -> END
```

Important details:

- The model is `deepseek-v4-flash` via `ChatOpenAI` with `base_url="https://api.deepseek.com"`.
- `InMemorySaver` is used as the top-level checkpointer.
- `InMemoryStore` is used as the graph store.
- The orchestrator has only one handoff tool: `transfer_to_assistant`.
- Gmail, LinkedIn, and internet agents are explicitly unavailable in the orchestrator prompt.
- Custom `repo_setup_progress` stream events are printed as `[repo-setup] ...`.
- Interrupts are detected from graph snapshots and resumed with `Command(resume=...)`.

## Routing Behavior

Routing starts in `src/middlewares/dynamic_agent_selector.py`.

The request goes to `repo_setup` when the latest user message contains a GitHub URL and setup-like language such as clone, repo, repository, install, setup, set up, or sandbox.

The request goes to `assistant` for Solari/sandbox/browser/desktop/code/bash tasks, local project references, or sandbox follow-up actions. Otherwise the graph falls back to the orchestrator, which normally delegates to assistant.

## Assistant Workflow

`src/subgraphs/assistant.py` handles general requests. It binds these tools:

- `read_skill`
- `bash`
- `solari_sandbox_create`
- `solari_sandbox_run_code`

The local `bash` tool can run commands only inside:

- this project root
- `CLONE_ROOT`, which is the parent directory of this project

****For background commands, `bash` writes logs under `.ultron_runs/`, returns the process id, log path, and a stop command using the process group.

The assistant graph includes a loop guard that blocks repeated calls to selected loop-prone tools, currently `snapshot` and `solari_sandbox_run_code`.

## Repository Setup Workflow

`src/subgraphs/repo_setup.py` builds a dedicated LangGraph workflow with these nodes:

```text
repo_setup_agent
tools
start_setup
fallback_gate
context_manager
finalize_setup
```

The bound repo setup tools are:

- `read_skill`
- `ask_question`
- `install_missing_setup_tools`
- `create_sandbox_clone_repo_and_install`

The workflow expects the model to load `repo_startup_discovery` before setup. If that skill has been read and a GitHub URL is present, `start_setup` deterministically invokes `create_sandbox_clone_repo_and_install` so setup does not depend on another model-generated tool call.

If the setup tool returns fallback questions, `fallback_gate` interrupts the graph and waits for user input. Responses such as `yes`, `approve`, `ok`, or `allow` are normalized into an approval payload.

## Repository Setup Safety Model

`create_sandbox_clone_repo_and_install` enforces the main safety rule:

1. Validate that the URL is a GitHub HTTPS or SSH URL.
2. Create or connect to a Solari sandbox.
3. Run the assembled Python setup script inside the sandbox.
4. Parse sandbox output and progress lines.
5. Only if all sandbox gate statuses pass, clone/install locally.
6. If any gate fails, skip local clone/install and return recovery questions when possible.

Local clone/install is hardwired on in the tool:

```python
install_on_user_device = True
```

Even so, local installation is blocked unless the sandbox gate passes.

## Sandbox Gate

The local machine is touched only when all of these text statuses appear with `0` in sandbox output and the Solari execution itself has no error:

- `REPO_SECURITY_STATUS 0`
- `REPO_SOCKET_MCP_STATUS 0`
- `REPO_SMOKE_STATUS 0`
- `REPO_TEST_STATUS 0`
- `REPO_SETUP_STATUS 0`

The current test gate is named like a test run, but it is really a test-file check. `src/sandbox_tests/test_checks.py.tmpl` checks whether a `tests/` directory exists and whether recognizable test files inside it are readable and non-empty. If there is no tests directory, the sandbox reports that fact and continues.

## Sandbox Script Assembly

`src/nodes/script.py` assembles one Python script from ordered fragments:

```text
core.py.tmpl
repository.py.tmpl
security.py.tmpl
discovery.py.tmpl
smoke.py.tmpl
test_checks.py.tmpl
socket_mcp.py.tmpl
main_flow.py.tmpl
```

The final script receives these substituted runtime values:

- `repo_url`
- `repo_name`
- `env_overrides`
- `startup_command`
- `socket_api_token`

Socket token environment variables are separated from normal repository env overrides before rendering, so app credentials and Socket credentials are handled differently.

## Sandbox Phases

| Fragment | Responsibility |
| --- | --- |
| `core.py.tmpl` | Command runner, bootstrap helpers, runtime detection, package-manager setup |
| `repository.py.tmpl` | Safe reads, ignore rules, file inventory, manifest detection |
| `security.py.tmpl` | Static suspicious-pattern scan before install/run |
| `discovery.py.tmpl` | Docs, env hints, README command extraction, repo profile JSON |
| `smoke.py.tmpl` | Python/Node/Go/Rust/Make smoke command discovery |
| `test_checks.py.tmpl` | Generic checks for test-like files under `tests/` |
| `socket_mcp.py.tmpl` | Dependency extraction and Socket MCP `depscore` scan |
| `main_flow.py.tmpl` | Clone, manifest reporting, install, smoke, test checks, final statuses |

The sandbox emits machine-readable lines such as `MANIFESTS_FOUND_BEGIN`, `INSTALL_END`, `REPO_SMOKE_STATUS`, and `REPO_PROFILE_JSON_BEGIN/END`. The host code parses these lines in `src/nodes/repo_setup_output.py`.

## Local Clone And Install

`src/nodes/local_setup.py` owns local setup after sandbox approval.

Local clone destination:

```text
/home/abhishek/Documents/projects
```

That is the parent directory of this GitReady project, so target repositories are cloned beside GitReady rather than inside it.

Supported dependency manifests and installers include:

- Node: `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `bun.lockb`
- Python: `pyproject.toml`, `uv.lock`, `requirements*.txt`, `Pipfile`, `poetry.lock`, `environment.yml`
- Go: `go.mod`
- Rust: `Cargo.toml`
- Ruby: `Gemfile`
- PHP: `composer.json`

If a target path already exists and is a Git repo, clone is skipped and dependency installation runs in the existing folder. If the target exists but is not a Git repo, setup fails instead of overwriting it.

## Missing Local Tool Installation

`install_missing_setup_tools` can install an allowlist of setup tools only after explicit approval.

Allowlisted tools include Python, Node/npm, pnpm, yarn, uv, poetry, pipenv, Go, Rust/Cargo, Bundler, Composer, and conda. Installation commands use non-interactive `apt-get` where configured, `npm install -g` for some Node package managers, or `python3 -m pip install --user` for Python package tools.

There is no automatic installer configured for `conda`.

## Final Setup Report

`src/nodes/repo_setup_summary.py` creates the final user-facing result. It reports:

- pass/fail status
- sandbox id and sandbox path
- static security scan status
- Socket MCP dependency scan status
- smoke run status
- test-file check status
- overall setup gate status
- discovered manifests
- likely start command
- local path when local setup completed
- sandbox console URL when available

The final message also derives a likely start command from README smoke candidates, Node scripts, Python entrypoints, or ecosystem defaults such as `go run .`, `cargo run`, or `make run`.

## Current Working Tree Notes

At the time of this report update, the working tree has pre-existing uncommitted changes:

- `README.md` changed the project name from ULTRON to GitReady, though the heading is currently `##GitReady` without a space.
- `main.py` changed the terminal prompt from `You:` to `Link:`.
- `src/nodes/local.py` is deleted from the working tree.
- `src/nodes/local_setup.py` is the current local setup module.
- `src/subgraphs/repo_setup_messages.py`, `src/subgraphs/repo_setup_prompt.py`, and `src/subgraphs/repo_setup_summary.py` are deleted from the working tree.
- Repo setup message helpers now live at `src/middlewares/repo_setup_messages.py`.
- Repo setup summary formatting now lives at `src/nodes/repo_setup_summary.py`.
- `src/subgraphs/repo_setup.py`, `src/tools/bash.py`, and `src/nodes/sandbox_repo_clone.py` import from the new locations.
- `report.md` itself is currently untracked.

These notes describe the current filesystem state, not necessarily committed history.

## Gaps And Risks

1. The README test command is stale because there is no `tests/` directory.
2. `pyproject.toml` still names the package `ultron` while the README/report use GitReady.
3. Several user-facing strings still mention ULTRON.
4. The repo setup prompt is embedded directly in `src/subgraphs/repo_setup.py`; the old separate prompt module is deleted.
5. The sandbox "test" gate checks test-file presence/readability, not actual test execution.
6. The sandbox gate depends on text-line parsing, which is easy to break with typoed prefixes.
7. `.gitignore` ignores `package-lock.json` globally, which can be wrong for Node examples or future Node app code that should commit lockfiles.
8. Local tool installation uses system package managers and global installers; it is approval-gated, but still needs careful user-facing explanation before use.
9. The repo has generated `__pycache__` files on disk, though `.gitignore` should keep them out of version control.

## Recommended Next Work

1. Restore or create a focused local test suite for routing, sandbox script rendering, output parsing, and local installer command selection.
2. Decide whether the canonical name is GitReady or ULTRON, then align README, `pyproject.toml`, prompts, paths, and user-facing messages.
3. Move the large repo setup system prompt back into a focused module, such as `src/config/repo_setup_prompt.py` or `src/subgraphs/repo_setup_prompt.py`.
4. Replace the sandbox text protocol with a final structured JSON result while keeping readable logs.
5. Upgrade `test_checks.py.tmpl` into a real test runner that detects safe test commands per ecosystem.
6. Add a small developer command surface, such as a `Makefile` or `justfile`, for `sync`, `test`, `compile-sandbox`, and `run`.
7. Revisit `.gitignore` so lockfiles are ignored only where intentionally generated, not across the whole repository by default.
8. Add regression tests for `dynamic_agent_selector.py` so GitHub setup requests consistently route to `repo_setup`.

## Summary

GitReady currently has a clear safety-oriented architecture: route the request, verify unknown repositories in Solari, run security/dependency/smoke/test-file gates, and only then clone/install locally. The current setup is functional in shape, but the documentation, naming, tests, and prompt/module organization need cleanup so the project is easier to maintain and safer to evolve.

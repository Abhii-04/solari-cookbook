# ULTRON

ULTRON is a local CLI agent built with LangGraph. It routes user requests between a
general assistant workflow and a repository setup workflow, with Solari sandbox
support for isolated code execution.

The agent can:

- answer general reasoning, writing, editing, and planning requests
- run local bash commands in this workspace when needed
- create and use Solari sandboxes for isolated execution
- safely set up GitHub repositories by cloning, scanning, installing, and smoke-running
  them in a sandbox before installing locally

## Requirements

- Python 3.11+
- `uv`
- a DeepSeek API key
- a Solari API key if you want sandbox features

Create a local `.env` file:

```bash
DEEPSEEK_API_KEY=your_deepseek_key
SOLARI_API_KEY=your_solari_key
```

## Install

```bash
uv sync
```

## Start The Agent

```bash
uv run python main.py
```

You will see a prompt:

```text
You:
```

Type a request and press Enter. Use `exit` or `quit` to stop the agent.

## Repository Setup Flow

When you ask ULTRON to set up a GitHub repository, it uses the dedicated repo
setup workflow:

1. Creates a Solari sandbox.
2. Clones the target repository into the sandbox.
3. Runs a static security scan before installing or running code.
4. Installs dependencies in the sandbox.
5. Runs a smoke command discovered from README files, manifests, and entrypoints.
6. Clones and installs locally only after the sandbox checks pass.

At the end of a successful setup, ULTRON prints the local path, detected start
command, project open command, and sandbox console URL when available.

Example:

```text
set up https://github.com/owner/repo.git
```

## Local Development

Run the tests with:

```bash
uv run python -m unittest discover -s tests
```

Run only the repository setup tests with:

```bash
uv run python -m unittest tests.test_repo_setup
```

## Project Layout

```text
main.py                 CLI entrypoint
src/agent.py            top-level LangGraph orchestrator
src/subgraphs/          assistant and repo setup workflows
src/nodes/              routing, local setup, and sandbox setup helpers
src/tools/              local bash, skill reading, and Solari tools
tests/                  unit tests
examples/               inherited Solari cookbook examples
```



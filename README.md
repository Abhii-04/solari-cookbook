## GitReady

GitReady isa LangGraph-based AI agent that converts ambiguous GitHub repository setup requests into an end-to-end
workflow for repository discovery, environment analysis, dependency installation, testing, and smoke execution.

Why I built this?

- It aims to help non tech people to use opensoource projects and applications 
- User can test an application on their own set of tests ( they need to update the tests in sandbox_tests folder)

* This is still a MVP and not an end to end product but it can work with smaller repos as of now like flask apps, web applicaitons etc , I havent tested it on OpenCV and other such repos as of 12/09/2026 .

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
gitready / >>
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


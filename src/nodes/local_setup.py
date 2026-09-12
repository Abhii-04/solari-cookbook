import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLONE_ROOT = PROJECT_ROOT.parent
DOC_FILE_NAMES = [
    "README.md",
    "README.rst",
    "README.txt",
    "docs/README.md",
    "CONTRIBUTING.md",
    "DEVELOPMENT.md",
    "INSTALL.md",
]


def repo_name_from_url(repo_url: str) -> str:
    """ extracts a safe local folder name from a github repo url"""
    name = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip(".-")
    if not name:
        raise ValueError("Could not determine a repository folder name from the URL.")
    return name


def is_supported_git_url(repo_url: str) -> bool:
    return bool(
        re.match(r"^https://github\.com/[^/\s]+/[^/\s]+(?:\.git)?/?$", repo_url)
        or re.match(r"^git@github\.com:[^/\s]+/[^/\s]+(?:\.git)?$", repo_url)
    )


def _run(command: list[str], cwd: Path, timeout: int = 900) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {
            "command": " ".join(command),
            "returncode": 127,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"Command timed out after {timeout} seconds.",
        }

    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _run_shell(command: str, cwd: Path, timeout: int = 900) -> dict[str, Any]:
    """run command as per model requested on local machine"""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"Command timed out after {timeout} seconds.",
        }

    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _has(command: str) -> bool:
    """checks if a command/program exist in the machine or systems PATH."""
    return shutil.which(command) is not None


def _missing_tools_from_results(results: list[dict[str, Any]]) -> list[str]:
    """scan command results for command not found errors"""
    missing = set()
    for result in results:
        if result.get("returncode") != 127:
            continue
        stderr = str(result.get("stderr", ""))
        match = re.search(r"Command not found: ([^\s]+)", stderr)
        if match:
            missing.add(match.group(1))
    return sorted(missing)


def _append_result(results: list[dict[str, Any]], command: list[str], cwd: Path) -> None:
    """Runs a command and seperate its reults with cwd."""
    result = _run(command, cwd) #uses run function to run a command locally
    result["cwd"] = str(cwd)
    results.append(result)


def _python_venv_candidates() -> list[str]:
    """Finds available python to create virtual environments."""
    candidates = []
    for command in ["python3.11", "python3.10", "python3.12", "python3"]:
        if _has(command):
            candidates.append(command)
    return candidates


def _create_python_venv(project_path: Path, results: list[dict[str, Any]]) -> bool:
    """creates .venv using uv or python -m venv ."""
    if (project_path / ".venv" / "bin" / "python").exists():
        return True

    interpreters = _python_venv_candidates()
    if not interpreters:
        results.append(_missing_tool_result("python3", project_path))
        return False

    commands = []
    if _has("uv"):
        commands.append(["uv", "venv", "--python", "3.11"])
        commands.extend([["uv", "venv", "--python", interpreter] for interpreter in interpreters])
    commands.extend([[interpreter, "-m", "venv", ".venv"] for interpreter in interpreters])

    attempt_indexes = []

    #Command in run using subprocess and _run function
    for command in commands:
        result = _run(command, project_path)
        result["cwd"] = str(project_path)
        results.append(result)
        attempt_indexes.append(len(results) - 1)
        if result["returncode"] == 0:
            for index in attempt_indexes[:-1]:
                results[index]["nonfatal"] = True
            return True

    if any(command[1:3] == ["-m", "venv"] for command in commands):
        results.append(_missing_tool_result("python3-venv", project_path))
    return False


def _is_ignored_path(path: Path) -> bool:
    """these directories are filtered out ."""
    ignored_parts = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
    }
    return any(part in ignored_parts for part in path.parts)


def _read_text_safely(path: Path, max_chars: int = 20_000) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"path": str(path), "readable": False, "content": "", "truncated": False}

    return {
        "path": str(path),
        "readable": True,
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def _doc_files(repo_path: Path) -> list[Path]:
    """finds common documentation files."""
    return [repo_path / name for name in DOC_FILE_NAMES if (repo_path / name).is_file()]


def _file_inventory(repo_path: Path, limit: int = 5000) -> dict[str, Any]:
    """builds a bounded list of repo files."""
    files = []
    total = 0
    for path in sorted(repo_path.rglob("*")):
        rel = path.relative_to(repo_path)
        if _is_ignored_path(rel) or not path.is_file():
            continue
        total += 1
        if len(files) < limit:
            files.append(str(rel))
    return {"total": total, "shown": files, "truncated": total > len(files)}


def _package_scripts(repo_path: Path) -> dict[str, Any]:
    """reads package.json scripts."""
    path = repo_path / "package.json"
    if not path.is_file():
        return {}
    try:
        package = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    scripts = package.get("scripts") if isinstance(package, dict) else {}
    return scripts if isinstance(scripts, dict) else {}


def _python_entrypoints(repo_path: Path) -> list[str]:
    """finds likely Python entry files like main.py, app.py, manage.py."""
    preferred_names = {"main.py", "app.py", "server.py", "run.py", "cli.py", "manage.py", "__main__.py"}
    entrypoints = []
    for path in sorted(repo_path.rglob("*.py")):
        rel = path.relative_to(repo_path)
        if _is_ignored_path(rel):
            continue
        if path.name in preferred_names:
            entrypoints.append(str(rel))
    return entrypoints[:50]


def _manifest_dirs(repo_path: Path, names: set[str], prefixes: tuple[str, ...] = ()) -> list[Path]:
    dirs = set()
    for path in repo_path.rglob("*"):
        if _is_ignored_path(path.relative_to(repo_path)):
            continue
        if path.is_file() and _is_dependency_manifest(path, repo_path, names, prefixes):
            dirs.add(path.parent)
    return sorted(dirs, key=lambda item: (len(item.relative_to(repo_path).parts), str(item)))


def _is_dependency_manifest(
    path: Path,
    repo_path: Path,
    names: set[str],
    prefixes: tuple[str, ...] = (),
) -> bool:
    rel = path.relative_to(repo_path)
    if path.name in names:
        return True

    if not prefixes or not path.name.startswith(prefixes):
        return False

    non_project_dirs = {
        "doc",
        "docs",
        "example",
        "examples",
        "fixture",
        "fixtures",
        "sample",
        "samples",
        "test",
        "tests",
    }
    if any(part.lower() in non_project_dirs for part in rel.parts[:-1]):
        return False

    return True

#Python dependencies installation part-----------------------------------------------------------
def _requirement_files(project_path: Path) -> list[Path]:
    return sorted(
        path
        for path in project_path.glob("*.txt")
        if path.name.startswith(("requirement", "requirements"))
    )


def _install_python_dependencies(project_path: Path, results: list[dict[str, Any]]) -> None:
    if not _has("python3") and not _has("uv"):
        results.append(_missing_tool_result("python3", project_path))
        return

    if (project_path / "uv.lock").exists():
        _append_result(results, ["uv", "sync"], project_path)
        return

    if (project_path / "poetry.lock").exists() and (project_path / "pyproject.toml").exists():
        _append_result(results, ["poetry", "install"], project_path)
        return

    requirement_files = _requirement_files(project_path)
    if requirement_files and _has("uv"):
        if not _create_python_venv(project_path, results):
            return
        for requirements_file in requirement_files:
            _append_result(
                results,
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    ".venv/bin/python",
                    "-r",
                    requirements_file.name,
                ],
                project_path,
            )
        return

    if requirement_files and _has("python3"):
        if not _create_python_venv(project_path, results):
            return
        for requirements_file in requirement_files:
            _append_result(
                results,
                [".venv/bin/python", "-m", "pip", "install", "-r", requirements_file.name],
                project_path,
            )
        return

    if (project_path / "pyproject.toml").exists():
        _append_result(results, ["uv", "sync"], project_path)
        return

    if (project_path / "Pipfile").exists():
        _append_result(results, ["pipenv", "install"], project_path)
        return

    if (project_path / "environment.yml").exists():
        _append_result(
            results,
            ["conda", "env", "update", "-f", "environment.yml"],
            project_path,
        )

#Node dependencies installation part------------------------------------------------------------

def _install_node_dependencies(project_path: Path, results: list[dict[str, Any]]) -> None:
    if not (project_path / "package.json").exists():
        return

    if (project_path / "pnpm-lock.yaml").exists():
        if not _has("pnpm"):
            results.append(_missing_tool_result("pnpm", project_path))
            return
        _append_result(results, ["pnpm", "install"], project_path)
    elif (project_path / "yarn.lock").exists():
        if not _has("yarn"):
            results.append(_missing_tool_result("yarn", project_path))
            return
        _append_result(results, ["yarn", "install"], project_path)
    elif (project_path / "bun.lockb").exists() or (project_path / "bun.lock").exists():
        if not _has("bun"):
            results.append(_missing_tool_result("bun", project_path))
            return
        _append_result(results, ["bun", "install"], project_path)
    elif (project_path / "package-lock.json").exists():
        if not _has("npm"):
            results.append(_missing_tool_result("npm", project_path))
            return
        _append_result(results, ["npm", "ci"], project_path)
    else:
        if not _has("npm"):
            results.append(_missing_tool_result("npm", project_path))
            return
        _append_result(results, ["npm", "install"], project_path)


def _missing_tool_result(tool_name: str, cwd: Path) -> dict[str, Any]:
    return {
        "command": tool_name,
        "returncode": 127,
        "stdout": "",
        "stderr": f"Command not found: {tool_name}",
        "cwd": str(cwd),
        "missing_tool": tool_name,
    }


def _install_command_for_tool(tool_name: str) -> str | None:
    if tool_name in {"python", "python3", "pip", "python3-venv"}:
        return "sudo -n apt-get update && sudo -n apt-get install -y python3 python3-pip python3-venv"
    if tool_name in {"node", "nodejs", "npm"}:
        return "sudo -n apt-get update && sudo -n apt-get install -y nodejs npm"
    if tool_name in {"pnpm", "yarn"}:
        if _has("corepack"):
            return f"corepack enable {tool_name}"
        if _has("npm"):
            return f"npm install -g {tool_name}"
        return None
    if tool_name in {"uv", "poetry", "pipenv"}:
        return f"python3 -m pip install --user {tool_name}"
    if tool_name in {"go", "golang"}:
        return "sudo -n apt-get update && sudo -n apt-get install -y golang-go"
    if tool_name in {"cargo", "rust", "rustc"}:
        return "sudo -n apt-get update && sudo -n apt-get install -y cargo"
    if tool_name == "bundle":
        return "sudo -n apt-get update && sudo -n apt-get install -y ruby-bundler"
    if tool_name == "composer":
        return "sudo -n apt-get update && sudo -n apt-get install -y composer"
    if tool_name == "conda":
        return None
    return None


@tool
def install_missing_setup_tools(tool_names: list[str], user_approved: bool = False) -> dict[str, Any]:
    """Install a small allowlist of missing developer setup tools on the local machine."""
    if not user_approved:
        return {
            "ok": False,
            "error": "Installation skipped because the user has not approved installing tools locally.",
        }

    allowed_names = {
        "python", "python3", "pip", "python3-venv", "node", "nodejs", "npm", "pnpm", "yarn", "uv", "poetry", "pipenv",
        "go", "golang", "cargo", "rust", "rustc", "bundle", "composer", "conda",
    }
    results = []
    for tool_name in sorted(set(tool_names)):
        normalized = tool_name.strip().lower()
        if normalized not in allowed_names:
            results.append(
                {
                    "tool": tool_name,
                    "ok": False,
                    "error": "Tool is not in the setup installer allowlist.",
                }
            )
            continue

        command = _install_command_for_tool(normalized)
        if command is None:
            results.append(
                {
                    "tool": tool_name,
                    "ok": False,
                    "error": "No safe automatic installer is configured for this tool.",
                }
            )
            continue

        result = _run_shell(command, PROJECT_ROOT)
        result["tool"] = normalized
        result["ok"] = result["returncode"] == 0
        results.append(result)

    return {
        "ok": all(result.get("ok") for result in results),
        "results": results,
    }

#Install other language dependencies---------------------------------------------------------
def _install_other_dependencies(project_path: Path, results: list[dict[str, Any]]) -> None:
    if (project_path / "go.mod").exists():
        _append_result(results, ["go", "mod", "download"], project_path)

    if (project_path / "Cargo.toml").exists():
        _append_result(results, ["cargo", "fetch"], project_path)

    if (project_path / "Gemfile").exists():
        _append_result(results, ["bundle", "install"], project_path)

    if (project_path / "composer.json").exists():
        _append_result(results, ["composer", "install"], project_path)


def _install_dependencies(repo_path: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    python_dirs = _manifest_dirs(
        repo_path,
        {"uv.lock", "pyproject.toml", "Pipfile", "poetry.lock", "environment.yml"},
        ("requirement", "requirements"),
    )
    node_dirs = _manifest_dirs(repo_path, {"package.json"})
    other_dirs = _manifest_dirs(repo_path, {"go.mod", "Cargo.toml", "Gemfile", "composer.json"})

    for project_path in python_dirs:
        _install_python_dependencies(project_path, results)
    for project_path in node_dirs:
        _install_node_dependencies(project_path, results)
    for project_path in other_dirs:
        _install_other_dependencies(project_path, results)

    return results


def _install_results_ok(results: list[dict[str, Any]]) -> bool:
    return all(result["returncode"] == 0 or result.get("nonfatal") for result in results)


def _manifest_summary(repo_path: Path) -> list[str]:
    manifest_names = {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "pyproject.toml",
        "uv.lock",
        "requirement.txt",
        "requirements.txt",
        "Pipfile",
        "poetry.lock",
        "environment.yml",
        "go.mod",
        "Cargo.toml",
        "Gemfile",
        "composer.json",
    }
    manifests = []
    for path in repo_path.rglob("*"):
        if _is_ignored_path(path.relative_to(repo_path)):
            continue
        if path.is_file() and _is_dependency_manifest(
            path,
            repo_path,
            manifest_names,
            ("requirement", "requirements"),
        ):
            manifests.append(str(path.relative_to(repo_path)))
    return sorted(manifests)


def _repo_profile(repo_path: Path) -> dict[str, Any]:
    docs = []
    for path in _doc_files(repo_path):
        item = _read_text_safely(path)
        item["path"] = str(path.relative_to(repo_path))
        docs.append(item)

    return {
        "repo_path": str(repo_path),
        "files": _file_inventory(repo_path),
        "docs": docs,
        "manifests": _manifest_summary(repo_path),
        "manifest_contents": [
            dict(_read_text_safely(repo_path / manifest, max_chars=10_000), path=manifest)
            for manifest in _manifest_summary(repo_path)
            if (repo_path / manifest).is_file()
        ],
        "entrypoints": {
            "python": _python_entrypoints(repo_path),
            "node_scripts": _package_scripts(repo_path),
            "go": (repo_path / "go.mod").exists(),
            "rust": (repo_path / "Cargo.toml").exists(),
            "ruby": (repo_path / "Gemfile").exists(),
            "php": (repo_path / "composer.json").exists(),
            "make": (repo_path / "Makefile").exists(),
        },
    }


@tool
def clone_repo_and_install_dependencies(
    repo_url: str,
    sandbox_checks_passed: bool = False,
    sandbox_test_passed: bool = False,
) -> dict[str, Any]:
    """Clone a Git repository beside this project and install dependencies from common manifest files."""
    if not (sandbox_checks_passed or sandbox_test_passed):
        return {
            "ok": False,
            "repo_url": repo_url,
            "local_install_skipped": True,
            "error": "Local clone/install is blocked until the repository passes sandbox security, install, and smoke checks.",
        }

    if not is_supported_git_url(repo_url):
        return {
            "ok": False,
            "repo_url": repo_url,
            "error": "Only GitHub repository URLs are supported, for example https://github.com/owner/repo.",
        }

    CLONE_ROOT.mkdir(parents=True, exist_ok=True)
    repo_name = repo_name_from_url(repo_url)
    repo_path = CLONE_ROOT / repo_name

    if repo_path.exists():
        if not repo_path.is_dir() or not (repo_path / ".git").exists():
            return {
                "ok": False,
                "repo_url": repo_url,
                "clone_root": str(CLONE_ROOT),
                "repo_path": str(repo_path),
                "error": "Target path already exists but is not a cloned Git repository.",
            }
        clone_result = {
            "command": "git clone -- " + repo_url + " " + str(repo_path),
            "returncode": 0,
            "stdout": "",
            "stderr": "Target repository already exists locally; skipped clone and installed dependencies in the existing folder.",
        }
    else:
        clone_result = _run(["git", "clone", "--", repo_url, str(repo_path)], CLONE_ROOT)
        if clone_result["returncode"] != 0:
            return {
                "ok": False,
                "repo_url": repo_url,
                "clone_root": str(CLONE_ROOT),
                "repo_path": str(repo_path),
                "clone": clone_result,
            }

    repo_profile = _repo_profile(repo_path)
    install_results = _install_dependencies(repo_path)

    return {
        "ok": _install_results_ok(install_results),
        "repo_url": repo_url,
        "clone_root": str(CLONE_ROOT),
        "repo_path": str(repo_path),
        "manifests_found": _manifest_summary(repo_path),
        "repo_profile": repo_profile,
        "clone": clone_result,
        "install_results": install_results,
        "missing_tools": _missing_tools_from_results(install_results),
    }

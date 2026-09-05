import os
import subprocess
import time
from langchain_core.tools import tool
import pathlib

from src.nodes.local import CLONE_ROOT

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
ALLOWED_ROOTS = (PROJECT_ROOT, CLONE_ROOT)
BACKGROUND_PROCESSES: list[subprocess.Popen] = []


def safe_path_for_project(path: str) -> pathlib.Path:
    """Resolve a path and ensure it stays inside the workspace or local clone root."""
    if not isinstance(path, str):
        raise TypeError("path must be a string")

    if not path:
        path = "."

    requested_path = pathlib.Path(path)
    if requested_path.is_absolute():
        resolved_path = requested_path.resolve()
    else:
        resolved_path = (PROJECT_ROOT / requested_path).resolve()

    for root in ALLOWED_ROOTS:
        try:
            resolved_path.relative_to(root)
            return resolved_path
        except ValueError:
            continue

    raise ValueError(
        f"Path {path} is outside the allowed local roots: "
        f"{', '.join(str(root) for root in ALLOWED_ROOTS)}."
    )


@tool
def bash(path: str, command: str, timeout: int = 60, background: bool = False) -> str:
    """Run a local shell command in an allowed project or cloned repository directory."""
    p = safe_path_for_project(path)
    if not p.exists():
        return f"ERROR: {path} does not exist"

    if not p.is_dir():
        return f"ERROR: {path} is not a directory"

    if background:
        log_dir = p / ".ultron_runs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"run-{int(time.time())}.log"
        log_file = log_path.open("w")
        try:
            process = subprocess.Popen(
                command,
                cwd=p,
                shell=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        finally:
            log_file.close()

        time.sleep(2)
        if process.poll() is None:
            BACKGROUND_PROCESSES.append(process)
            return (
                f"RUNNING pid={process.pid}\n"
                f"CWD {p}\n"
                f"LOG {log_path}\n"
                f"STOP kill -TERM -{os.getpgid(process.pid)}"
            )

        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        return f"EXIT {process.returncode}\nLOG {log_path}\n{log_text[-4000:]}"

    try:
        result = subprocess.run(
            command,
            cwd=p,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = f"TIMEOUT after {timeout}s\n"
        if exc.stdout:
            output += f"STDOUT:\n{exc.stdout}"
        if exc.stderr:
            output += f"STDERR:\n{exc.stderr}"
        return output

    output = f"EXIT {result.returncode}\n"
    if result.stdout:
        output += f"STDOUT:\n{result.stdout}"
    if result.stderr:
        output += f"STDERR:\n{result.stderr}"
    return output

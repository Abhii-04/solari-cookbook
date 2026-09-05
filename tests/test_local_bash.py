import os
import signal
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.tools.bash import (
    BACKGROUND_PROCESSES,
    CLONE_ROOT,
    PROJECT_ROOT,
    bash,
    safe_path_for_project,
)


class LocalBashToolTests(unittest.TestCase):
    def test_safe_path_allows_project_relative_paths(self):
        self.assertEqual(safe_path_for_project(".").resolve(), PROJECT_ROOT)

    def test_safe_path_allows_absolute_sibling_clone_paths(self):
        with TemporaryDirectory(dir=CLONE_ROOT) as tmp:
            self.assertEqual(safe_path_for_project(tmp), Path(tmp).resolve())

    def test_safe_path_rejects_paths_outside_allowed_roots(self):
        with self.assertRaises(ValueError):
            safe_path_for_project("/etc")

    def test_bash_runs_with_requested_directory_as_cwd(self):
        with TemporaryDirectory(dir=CLONE_ROOT) as tmp:
            result = bash.invoke({"path": tmp, "command": "pwd"})

        self.assertIn(f"STDOUT:\n{tmp}\n", result)

    def test_bash_can_start_background_process(self):
        with TemporaryDirectory(dir=CLONE_ROOT) as tmp:
            result = bash.invoke(
                {
                    "path": tmp,
                    "command": "python3 -m http.server 0",
                    "background": True,
                }
            )

        self.assertIn("RUNNING pid=", result)
        self.assertIn("LOG ", result)
        self.assertIn("STOP kill -TERM -", result)
        pid = int(result.split("RUNNING pid=", 1)[1].splitlines()[0])
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        for process in BACKGROUND_PROCESSES:
            if process.pid == pid:
                process.wait(timeout=5)
                break


if __name__ == "__main__":
    unittest.main()

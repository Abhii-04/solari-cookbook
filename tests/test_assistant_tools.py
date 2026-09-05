import unittest
from pathlib import Path


class AssistantToolingTests(unittest.TestCase):
    def test_assistant_has_local_bash_and_prefers_it_for_local_requests(self):
        source = Path("src/subgraphs/assistant.py").read_text()

        self.assertIn("from src.tools.bash import bash", source)
        self.assertIn("self.tools = [read_skill, bash, solari_sandbox_create, solari_sandbox_run_code]", source)
        self.assertIn("If the user asks to run, inspect, list, or modify something on the local machine", source)
        self.assertIn("use the local bash tool, not Solari", source)
        self.assertIn("background=true", source)
        self.assertIn('loop_tools = {"snapshot", "solari_sandbox_run_code"}', source)


if __name__ == "__main__":
    unittest.main()

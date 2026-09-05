import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages

from src.nodes.context import (
    MAX_SUMMARY_CHARS,
    SUMMARY_MESSAGE_ID,
    compact_repo_setup_context,
)


class RepoSetupContextManagerTests(unittest.TestCase):
    def test_compacts_setup_tool_exchange_into_rolling_summary(self):
        tool_call_id = "call-1"
        messages = [
            HumanMessage(content="https://github.com/example/repo.git", id="human-1"),
            AIMessage(
                content="",
                id="ai-1",
                tool_calls=[
                    {
                        "name": "create_sandbox_clone_repo_and_install",
                        "args": {"repo_url": "https://github.com/example/repo.git"},
                        "id": tool_call_id,
                    }
                ],
            ),
            ToolMessage(
                name="create_sandbox_clone_repo_and_install",
                tool_call_id=tool_call_id,
                id="tool-1",
                content=json.dumps(
                    {
                        "ok": False,
                        "repo_url": "https://github.com/example/repo.git",
                        "repo_name": "repo",
                        "sandbox": {"sandbox_id": "sandbox-1", "control_url": "url"},
                        "sandbox_repo_path": "/workspace/repo",
                        "sandbox_repo_profile": {
                            "manifests": ["package.json"],
                            "files": {
                                "total": 2,
                                "shown": ["README.md", "package.json"],
                                "truncated": False,
                            },
                            "docs": [{"path": "README.md", "content": "npm start"}],
                            "manifest_contents": [
                                {"path": "package.json", "content": '{"scripts":{"start":"vite"}}'}
                            ],
                            "readme_smoke_candidates": ["npm start"],
                            "entrypoints": {"node_scripts": {"start": "vite"}},
                        },
                        "fallback_questions": ["May I install pnpm?"],
                        "local_install": {
                            "ok": False,
                            "repo_profile": {
                                "manifests": ["package.json"],
                                "files": {
                                    "total": 2,
                                    "shown": ["README.md", "package.json"],
                                    "truncated": False,
                                },
                                "docs": [{"path": "README.md", "content": "npm start"}],
                                "manifest_contents": [
                                    {"path": "package.json", "content": '{"scripts":{"start":"vite"}}'}
                                ],
                                "entrypoints": {"node_scripts": {"start": "vite"}},
                            },
                        },
                        "sandbox_install": {
                            "error": None,
                            "outputs": [
                                {
                                    "text": (
                                        "$ git clone -- https://github.com/example/repo.git /workspace/repo\n"
                                        "REPO_SECURITY_STATUS 0\n"
                                        "MISSING_TOOL pnpm\n"
                                        "REPO_SMOKE_STATUS 1\n"
                                        "REPO_SETUP_STATUS 1\n"
                                    )
                                }
                            ],
                        },
                    }
                ),
            ),
        ]

        update = compact_repo_setup_context({"messages": messages})
        compacted = add_messages(messages, update["messages"])

        self.assertEqual([message.id for message in compacted], ["human-1", SUMMARY_MESSAGE_ID])
        self.assertIn("sandbox_id=sandbox-1", compacted[-1].content)
        self.assertIn("sandbox_profile:", compacted[-1].content)
        self.assertIn("doc_excerpts=['README.md: npm start']", compacted[-1].content)
        self.assertIn("manifest_excerpts=['package.json:", compacted[-1].content)
        self.assertIn("readme_smoke_candidates=['npm start']", compacted[-1].content)
        self.assertIn("local_profile:", compacted[-1].content)
        self.assertIn("MISSING_TOOL pnpm", compacted[-1].content)
        self.assertIn("May I install pnpm?", compacted[-1].content)
        self.assertIn("=== Sandbox operations log ===", update["setup_logs"][0])

    def test_context_summary_message_is_replaced_on_each_compaction(self):
        original_messages = [
            ToolMessage(
                name="read_skill",
                tool_call_id="call-1",
                id="tool-1",
                content="startup docs",
            )
        ]
        first = compact_repo_setup_context(
            {
                "messages": original_messages
            }
        )
        second_messages = add_messages(original_messages, first["messages"])
        messages_with_second_tool = second_messages + [
            ToolMessage(
                name="read_skill",
                tool_call_id="call-2",
                id="tool-2",
                content="startup docs again",
            )
        ]
        second = compact_repo_setup_context({"messages": messages_with_second_tool})
        compacted = add_messages(messages_with_second_tool, second["messages"])

        self.assertEqual(
            [message.id for message in compacted if message.id == SUMMARY_MESSAGE_ID],
            [SUMMARY_MESSAGE_ID],
        )
        self.assertLessEqual(len(compacted[-1].content), MAX_SUMMARY_CHARS)


if __name__ == "__main__":
    unittest.main()

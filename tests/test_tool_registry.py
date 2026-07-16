import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import mcp


class TestToolRegistry(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await mcp.list_tools()}

    async def test_exposes_the_short_public_tool_names(self):
        self.assertEqual(
            set(self.tools),
            {
                "create_presentation",
                "add_slide",
                "update_slide",
                "apply_dark_theme",
                "export_thumbnails",
                "compose_slide",
                "delete_slide",
                "get_presentation",
            },
        )
        self.assertNotIn("slides_speaker_notes_experiment", self.tools)

    async def test_read_only_tools_are_annotated(self):
        for name in ("export_thumbnails", "get_presentation"):
            with self.subTest(tool=name):
                annotations = self.tools[name].annotations
                self.assertIsNotNone(annotations)
                self.assertTrue(annotations.readOnlyHint)
                self.assertFalse(annotations.destructiveHint)
                self.assertTrue(annotations.idempotentHint)
                self.assertTrue(annotations.openWorldHint)

    async def test_mutating_tools_are_annotated(self):
        expected_idempotency = {
            "create_presentation": False,
            "add_slide": False,
            "update_slide": True,
            "apply_dark_theme": True,
            "compose_slide": True,
        }

        for name, idempotent in expected_idempotency.items():
            with self.subTest(tool=name):
                annotations = self.tools[name].annotations
                self.assertIsNotNone(annotations)
                self.assertFalse(annotations.readOnlyHint)
                self.assertFalse(annotations.destructiveHint)
                self.assertEqual(annotations.idempotentHint, idempotent)
                self.assertTrue(annotations.openWorldHint)


if __name__ == "__main__":
    unittest.main()

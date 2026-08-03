import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import get_slide_elements


class TestGetSlideElements(unittest.IsolatedAsyncioTestCase):
    async def test_returns_ids_text_sizes_and_transforms_for_requested_slide(self):
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = {
            "presentationId": "deck-1",
            "slides": [
                {"objectId": "slide-1", "pageElements": []},
                {
                    "objectId": "slide-2",
                    "pageElements": [
                        {
                            "objectId": "accent-rule",
                            "size": {
                                "width": {"magnitude": 72, "unit": "PT"},
                                "height": {"magnitude": 4, "unit": "PT"},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": 50,
                                "translateY": 77,
                                "unit": "PT",
                            },
                            "shape": {"shapeType": "RECTANGLE"},
                        },
                        {
                            "objectId": "heading",
                            "shape": {
                                "shapeType": "TEXT_BOX",
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "Что будет ",}},
                                        {"textRun": {"content": "на выходе\n",}},
                                    ]
                                },
                            },
                        },
                    ],
                },
            ],
        }

        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = json.loads(await get_slide_elements("deck-1", 2))

        self.assertEqual(result["slideObjectId"], "slide-2")
        self.assertEqual(result["elements"][0]["objectId"], "accent-rule")
        self.assertEqual(result["elements"][0]["shapeType"], "RECTANGLE")
        self.assertEqual(result["elements"][0]["transform"]["translateY"], 77)
        self.assertEqual(result["elements"][1]["text"], "Что будет на выходе")

    async def test_rejects_an_out_of_bounds_slide_index(self):
        service = MagicMock()
        service.presentations.return_value.get.return_value.execute.return_value = {
            "slides": [{"objectId": "slide-1", "pageElements": []}]
        }

        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await get_slide_elements("deck-1", 2)

        self.assertIn("out of bounds", result)
        self.assertIn("1-1", result)


if __name__ == "__main__":
    unittest.main()

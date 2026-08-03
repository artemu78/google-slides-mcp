import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import BatchUpdateInput, batch_update


class TestBatchUpdate(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_hex_text_foreground_color_to_optional_color(self):
        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.batchUpdate.return_value.execute.return_value = {"replies": []}
        params = BatchUpdateInput(
            presentation_id="deck-1",
            requests=[
                {
                    "updateTextStyle": {
                        "objectId": "text-box-1",
                        "textRange": {"type": "ALL"},
                        "style": {"foregroundColor": "#0070C0"},
                        "fields": "foregroundColor",
                    }
                }
            ],
        )

        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await batch_update(params)

        self.assertEqual(result, '{\n  "replies": []\n}')
        request = presentations_api.batchUpdate.call_args.kwargs["body"]["requests"][0]
        self.assertEqual(
            request["updateTextStyle"]["style"]["foregroundColor"],
            {
                "opaqueColor": {
                    "rgbColor": {"red": 0.0, "green": 112 / 255.0, "blue": 192 / 255.0}
                }
            },
        )

    async def test_rejects_direct_rgb_text_foreground_color_before_api_call(self):
        service = MagicMock()
        params = BatchUpdateInput(
            presentation_id="deck-1",
            requests=[
                {
                    "updateTextStyle": {
                        "style": {
                            "foregroundColor": {
                                "rgbColor": {"red": 0, "green": 0.44, "blue": 0.75}
                            }
                        }
                    }
                }
            ],
        )

        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await batch_update(params)

        self.assertIn("Error validating batch update", result)
        self.assertIn("OptionalColor wrapper", result)
        service.presentations.assert_not_called()


if __name__ == "__main__":
    unittest.main()

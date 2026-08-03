import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import export_slide_thumbnail


class TestExportSlideThumbnail(unittest.IsolatedAsyncioTestCase):
    async def test_exports_only_the_requested_slide(self):
        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = {
            "slides": [
                {"objectId": "slide-1"},
                {"objectId": "slide-2"},
                {"objectId": "slide-3"},
            ]
        }
        thumbnail_request = presentations_api.pages.return_value.getThumbnail
        thumbnail_request.return_value.execute.return_value = {
            "contentUrl": "https://example.test/slide-2.png"
        }
        response = MagicMock(content=b"png-bytes")

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, "selected.png")
            with (
                patch("google_slides_mcp.get_slides_service", return_value=service),
                patch("google_slides_mcp.requests.get", return_value=response) as download,
            ):
                result = json.loads(await export_slide_thumbnail(
                    "deck-1",
                    2,
                    output_path,
                ))

            with open(output_path, "rb") as exported_file:
                self.assertEqual(exported_file.read(), b"png-bytes")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["slideIndex"], 2)
        self.assertEqual(result["slideObjectId"], "slide-2")
        thumbnail_request.assert_called_once_with(
            presentationId="deck-1",
            pageObjectId="slide-2",
            thumbnailProperties_thumbnailSize="LARGE",
            thumbnailProperties_mimeType="PNG",
        )
        download.assert_called_once_with("https://example.test/slide-2.png", timeout=30)
        response.raise_for_status.assert_called_once_with()

    async def test_rejects_out_of_bounds_index_before_thumbnail_request(self):
        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = {
            "slides": [{"objectId": "slide-1"}]
        }

        with (
            patch("google_slides_mcp.get_slides_service", return_value=service),
            patch("google_slides_mcp.requests.get") as download,
        ):
            result = await export_slide_thumbnail("deck-1", 2, "unused.png")

        self.assertIn("out of bounds", result)
        presentations_api.pages.return_value.getThumbnail.assert_not_called()
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()

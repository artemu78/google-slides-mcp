import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import get_icon_url, insert_icon, search_icons


class TestIconTools(unittest.IsolatedAsyncioTestCase):
    async def test_search_icons_returns_ranked_paginated_catalog_results(self):
        result = json.loads(await search_icons("arrow right", "outline", 3, 0))

        self.assertEqual(result["normalizedQuery"], "arrow-right")
        self.assertLessEqual(result["count"], 3)
        self.assertIn("arrow-right", result["icons"])
        self.assertEqual(result["icons"][0], "arrow-right")

    async def test_get_icon_url_uses_configured_public_png_layout(self):
        with patch.dict(os.environ, {"TABLER_ICONS_BASE_URL": "https://cdn.example.com/icons/"}):
            result = json.loads(await get_icon_url("arrow right", "outline", "light"))

        self.assertEqual(result["iconName"], "arrow-right")
        self.assertEqual(
            result["url"],
            "https://cdn.example.com/icons/light/outline/arrow-right.png",
        )

    async def test_get_icon_url_rejects_unknown_icon(self):
        with patch.dict(os.environ, {"TABLER_ICONS_BASE_URL": "https://cdn.example.com/icons"}):
            result = await get_icon_url("definitely-not-a-real-tabler-icon", "outline", "dark")

        self.assertIn("Unknown outline Tabler icon", result)
        self.assertIn("Call search_icons", result)

    async def test_insert_icon_creates_image_and_alt_text(self):
        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = {
            "slides": [{"objectId": "slide-1"}]
        }
        presentations_api.batchUpdate.return_value.execute.return_value = {"replies": []}

        with patch.dict(os.environ, {"TABLER_ICONS_BASE_URL": "https://cdn.example.com/icons"}), \
                patch("google_slides_mcp.get_slides_service", return_value=service):
            result = json.loads(await insert_icon(
                "deck-1", 1, "search", 40, 50, 24, 24, "outline", "light", "Search",
            ))

        self.assertEqual(result["iconName"], "search")
        request_body = presentations_api.batchUpdate.call_args.kwargs["body"]
        create_image = request_body["requests"][0]["createImage"]
        self.assertEqual(create_image["url"], "https://cdn.example.com/icons/light/outline/search.png")
        self.assertEqual(create_image["elementProperties"]["pageObjectId"], "slide-1")
        self.assertEqual(create_image["elementProperties"]["transform"]["translateX"], 40)
        self.assertEqual(
            request_body["requests"][1]["updatePageElementAltText"]["description"],
            "Search",
        )

    async def test_insert_icon_validates_configuration_before_google_api(self):
        service = MagicMock()
        with patch.dict(os.environ, {}, clear=True), \
                patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await insert_icon("deck-1", 1, "search", 0, 0, 24, 24)

        self.assertIn("TABLER_ICONS_BASE_URL is not configured", result)
        service.presentations.assert_not_called()


if __name__ == "__main__":
    unittest.main()

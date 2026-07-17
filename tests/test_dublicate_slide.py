import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import DublicateSlideInput, dublicate_slide


class TestDublicateSlide(unittest.IsolatedAsyncioTestCase):
    async def test_duplicates_slide_by_one_based_index(self):
        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = {
            "slides": [
                {"objectId": "slide-1"},
                {"objectId": "slide-2"},
            ]
        }
        presentations_api.batchUpdate.return_value.execute.return_value = {
            "replies": [
                {"duplicateObject": {"objectId": "slide-2-copy"}}
            ]
        }

        params = DublicateSlideInput(presentation_id="deck-1", slide_index=2)
        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await dublicate_slide(params)

        presentations_api.batchUpdate.assert_called_once_with(
            presentationId="deck-1",
            body={
                "requests": [
                    {"duplicateObject": {"objectId": "slide-2"}}
                ]
            },
        )
        self.assertEqual(
            json.loads(result),
            {
                "sourceSlideIndex": 2,
                "sourceSlideId": "slide-2",
                "duplicatedSlideId": "slide-2-copy",
            },
        )

    async def test_rejects_out_of_bounds_slide_index(self):
        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = {
            "slides": [{"objectId": "slide-1"}]
        }

        params = DublicateSlideInput(presentation_id="deck-1", slide_index=2)
        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await dublicate_slide(params)

        self.assertEqual(
            result,
            "Error: Slide index 2 out of bounds (Total slides: 1)",
        )
        presentations_api.batchUpdate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

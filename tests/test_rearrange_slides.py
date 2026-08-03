import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import RearrangeSlidesInput, rearrange_slides


class TestRearrangeSlides(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = MagicMock()
        self.presentations_api = self.service.presentations.return_value
        self.presentations_api.get.return_value.execute.return_value = {
            "slides": [
                {"objectId": "slide-1"},
                {"objectId": "slide-2"},
                {"objectId": "slide-3"},
                {"objectId": "slide-4"},
            ]
        }

    async def test_rearranges_requested_slides_and_preserves_unspecified_order(self):
        with patch("google_slides_mcp.get_slides_service", return_value=self.service):
            result = await rearrange_slides("deck-1", {1: 3, 4: 1})

        self.presentations_api.batchUpdate.assert_called_once_with(
            presentationId="deck-1",
            body={"requests": [
                {"updateSlidesPosition": {"slideObjectIds": ["slide-4"], "insertionIndex": 0}},
                {"updateSlidesPosition": {"slideObjectIds": ["slide-2"], "insertionIndex": 1}},
            ]},
        )
        self.assertEqual(
            json.loads(result),
            {
                "slideCount": 4,
                "requestedPositions": {"1": 3, "4": 1},
                "finalOrder": ["slide-4", "slide-2", "slide-1", "slide-3"],
                "movedSlideCount": 2,
            },
        )

    async def test_rejects_duplicate_destination_without_writing(self):
        with patch("google_slides_mcp.get_slides_service", return_value=self.service):
            result = await rearrange_slides("deck-1", {1: 2, 3: 2})

        self.assertEqual(result, "Error: Each requested new position must belong to exactly one slide.")
        self.presentations_api.batchUpdate.assert_not_called()

    async def test_rejects_out_of_range_positions_without_writing(self):
        with patch("google_slides_mcp.get_slides_service", return_value=self.service):
            result = await rearrange_slides("deck-1", {5: 1, 1: 6})

        self.assertEqual(
            result,
            "Error: Slide numbers out of bounds (valid range: 1-4): [5]",
        )
        self.presentations_api.batchUpdate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

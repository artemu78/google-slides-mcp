import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google_slides_mcp import UpdateSlideInput, update_slide


class TestUpdateSlide(unittest.IsolatedAsyncioTestCase):
    async def test_replaces_existing_speaker_notes_text_when_notes_object_present(self):
        presentation_payload = {
            "slides": [
                {
                    "objectId": "slide-1",
                    "pageElements": [],
                    "notesPage": {
                        "notesProperties": {
                            "speakerNotesObjectId": "speaker-notes-shape-1"
                        },
                        "pageElements": [
                            {
                                "objectId": "speaker-notes-shape-1",
                                "shape": {
                                    "text": {
                                        "textElements": [
                                            {
                                                "textRun": {
                                                    "content": "Old notes text"
                                                }
                                            }
                                        ]
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        }

        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = presentation_payload
        presentations_api.batchUpdate.return_value.execute.return_value = {}

        params = UpdateSlideInput(
            presentation_id="deck-1",
            slide_index=1,
            speaker_notes="New notes text",
        )

        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await update_slide(params)

        self.assertEqual(result, "Successfully updated slide 1")
        presentations_api.batchUpdate.assert_called_once()
        update_body = presentations_api.batchUpdate.call_args.kwargs["body"]
        self.assertIn(
            {
                "deleteText": {
                    "objectId": "speaker-notes-shape-1",
                    "textRange": {"type": "ALL"},
                }
            },
            update_body["requests"],
        )
        self.assertIn(
            {
                "insertText": {
                    "objectId": "speaker-notes-shape-1",
                    "text": "New notes text",
                }
            },
            update_body["requests"],
        )

    async def test_updates_speaker_notes_via_notes_properties_object_id(self):
        presentation_payload = {
            "slides": [
                {
                    "objectId": "slide-1",
                    "pageElements": [],
                    "notesPage": {
                        "notesProperties": {
                            "speakerNotesObjectId": "speaker-notes-shape-1"
                        },
                        "pageElements": [],
                    },
                }
            ]
        }

        service = MagicMock()
        presentations_api = service.presentations.return_value
        presentations_api.get.return_value.execute.return_value = presentation_payload
        presentations_api.batchUpdate.return_value.execute.return_value = {}

        params = UpdateSlideInput(
            presentation_id="deck-1",
            slide_index=1,
            speaker_notes="Talk track text",
        )

        with patch("google_slides_mcp.get_slides_service", return_value=service):
            result = await update_slide(params)

        self.assertEqual(result, "Successfully updated slide 1")
        presentations_api.batchUpdate.assert_called_once()
        update_body = presentations_api.batchUpdate.call_args.kwargs["body"]
        self.assertIn(
            {
                "insertText": {
                    "objectId": "speaker-notes-shape-1",
                    "text": "Talk track text",
                }
            },
            update_body["requests"],
        )


if __name__ == "__main__":
    unittest.main()

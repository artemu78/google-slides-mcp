import unittest
import sys
import os

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from google_slides_mcp import find_placeholder, find_speaker_notes_object_id

class TestFindPlaceholder(unittest.TestCase):

    def test_finds_correct_placeholder(self):
        # Mock Google Slides API response structure
        mock_elements = [
            {
                "objectId": "wrong-element-1",
                "image": {
                    "contentUrl": "http://example.com/image.png"
                }
            },
            {
                "objectId": "correct-title-id",
                "shape": {
                    "shapeType": "TEXT_BOX",
                    "placeholder": {
                        "type": "TITLE",
                        "parentObjectId": "some-layout-id"
                    }
                }
            },
            {
                "objectId": "correct-body-id",
                "shape": {
                    "shapeType": "TEXT_BOX",
                    "placeholder": {
                        "type": "BODY",
                        "parentObjectId": "some-layout-id"
                    }
                }
            }
        ]

        title_id = find_placeholder(mock_elements, 'TITLE')
        self.assertEqual(title_id, 'correct-title-id')

        body_id = find_placeholder(mock_elements, 'BODY')
        self.assertEqual(body_id, 'correct-body-id')

    def test_returns_none_if_not_found(self):
        mock_elements = [
            {
                "objectId": "random-id",
                "shape": {
                    "shapeType": "RECTANGLE"
                }
            }
        ]
        
        result = find_placeholder(mock_elements, 'TITLE')
        self.assertIsNone(result)

    def test_handles_empty_elements(self):
        result = find_placeholder([], 'TITLE')
        self.assertIsNone(result)

class TestFindSpeakerNotesObjectId(unittest.TestCase):
    def test_prefers_notes_properties_id(self):
        slide = {
            "notesPage": {
                "notesProperties": {"speakerNotesObjectId": "notes-shape-1"},
                "pageElements": []
            }
        }
        self.assertEqual(find_speaker_notes_object_id(slide), "notes-shape-1")

    def test_falls_back_to_speaker_notes_placeholder(self):
        slide = {
            "notesPage": {
                "pageElements": [
                    {
                        "objectId": "speaker-notes-shape",
                        "shape": {"placeholder": {"type": "SPEAKER_NOTES"}}
                    }
                ]
            }
        }
        self.assertEqual(find_speaker_notes_object_id(slide), "speaker-notes-shape")

    def test_falls_back_to_body_placeholder(self):
        slide = {
            "notesPage": {
                "pageElements": [
                    {
                        "objectId": "notes-body-shape",
                        "shape": {"placeholder": {"type": "BODY"}}
                    }
                ]
            }
        }
        self.assertEqual(find_speaker_notes_object_id(slide), "notes-body-shape")

    def test_returns_none_without_notes_shape(self):
        slide = {"notesPage": {"pageElements": []}}
        self.assertIsNone(find_speaker_notes_object_id(slide))

if __name__ == '__main__':
    unittest.main()

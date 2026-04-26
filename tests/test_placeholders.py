import unittest
import sys
import os

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We need to import the function to test. Since it's nested inside `update_slide`, 
# we'll extract it here for unit testing purposes.
def find_placeholder(elements, p_type):
    for el in elements:
        shape = el.get('shape')
        if shape and 'placeholder' in shape and shape['placeholder'].get('type') == p_type:
            return el.get('objectId')
    return None

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

if __name__ == '__main__':
    unittest.main()

import os
import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google_slides_mcp")

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/cloud-platform'
]

mcp = FastMCP("google_slides_mcp")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

def get_credentials():
    creds = None
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(script_dir, 'token.json')
    creds_path = os.path.join(script_dir, 'credentials.json')

    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                creds = None
        
        if not creds or not creds.valid:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"credentials.json not found in {script_dir}. "
                    "Please provide a Google Cloud OAuth 2.0 Client ID JSON file."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            
            # If we are in an MCP server context, we might not be able to open a browser
            # automatically or we might be in a remote environment.
            try:
                # Try to run local server (default)
                creds = flow.run_local_server(port=0, open_browser=True)
            except Exception as e:
                logger.warning(f"Could not open browser for authentication: {e}")
                logger.info("Falling back to manual authentication URL...")
                # Note: run_console is deprecated, but we can use run_local_server with open_browser=False
                creds = flow.run_local_server(port=0, open_browser=False)
                
        # Save the credentials for the next run
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            logger.info(f"Saved new token to {token_path}")
            
    return creds

def get_slides_service():
    creds = get_credentials()
    return build('slides', 'v1', credentials=creds)

def hex_to_rgb(hex_color: str) -> Dict[str, float]:
    """Converts a hex color string (e.g. #FFFFFF) to an RGB dict for Google Slides API."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    return {
        'red': int(hex_color[0:2], 16) / 255.0,
        'green': int(hex_color[2:4], 16) / 255.0,
        'blue': int(hex_color[4:6], 16) / 255.0
    }

# --- Models ---

class CreatePresentationInput(BaseModel):
    title: str = Field(..., description="The title of the new presentation.")

class AddSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    insertion_index: Optional[int] = Field(None, description="1-based index where to insert the slide. If omitted, adds to the end.", ge=1)
    layout_id: str = Field("TITLE_AND_BODY", description="The layout of the new slide (e.g., TITLE_AND_BODY, MAIN_POINT, SECTION_HEADER).")

class UpdateSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based index of the slide to update.", ge=1)
    title: Optional[str] = Field(None, description="New text for the title placeholder.")
    body: Optional[str] = Field(None, description="New text for the body/content placeholder.")
    speaker_notes: Optional[str] = Field(None, description="New text for the speaker notes.")
    background_color: Optional[str] = Field(None, description="Hex color for the slide background (e.g., #FFFFFF).")
    text_color: Optional[str] = Field(None, description="Hex color for the title and body text (e.g., #000000).")

class DeleteSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based index of the slide to delete.", ge=1)

# --- Tools ---

@mcp.tool(name="slides_create_presentation")
async def create_presentation(params: CreatePresentationInput) -> str:
    """Creates a new Google Slides presentation."""
    try:
        service = get_slides_service()
        presentation = service.presentations().create(body={'title': params.title}).execute()
        return json.dumps({
            "presentationId": presentation.get('presentationId'),
            "title": presentation.get('title'),
            "url": f"https://docs.google.com/presentation/d/{presentation.get('presentationId')}/edit"
        }, indent=2)
    except Exception as e:
        return f"Error creating presentation: {str(e)}"

@mcp.tool(name="slides_add_slide")
async def add_slide(params: AddSlideInput) -> str:
    """Adds a new slide to a presentation at a specified 1-based index."""
    try:
        service = get_slides_service()
        # If insertion_index is None, the API usually appends or we might need to know the count.
        # But for 'createSlide', leaving out 'insertionIndex' appends it.
        # Note: API expects 0-based index.
        requests = [{
            'createSlide': {
                'slideLayoutReference': {'predefinedLayout': params.layout_id}
            }
        }]
        
        if params.insertion_index is not None:
            requests[0]['createSlide']['insertionIndex'] = params.insertion_index - 1

        response = service.presentations().batchUpdate(
            presentationId=params.presentation_id,
            body={'requests': requests}
        ).execute()
        
        slide_id = response.get('replies')[0].get('createSlide').get('objectId')
        return f"Successfully added slide with ID: {slide_id}"
    except Exception as e:
        return f"Error adding slide: {str(e)}"

@mcp.tool(name="slides_update_slide")
async def update_slide(params: UpdateSlideInput) -> str:
    """Updates title, body, speaker notes, or styling of a slide by its 1-based index."""
    try:
        service = get_slides_service()
        # 1. Get presentation to find the slide objectId at the given index
        presentation = service.presentations().get(presentationId=params.presentation_id).execute()
        slides = presentation.get('slides', [])
        
        if params.slide_index > len(slides):
            return f"Error: Slide index {params.slide_index} out of bounds (Total slides: {len(slides)})"
        
        slide = slides[params.slide_index - 1]
        slide_id = slide.get('objectId')
        
        requests = []
        
        # Helper to find placeholder
        def find_placeholder(elements, p_type):
            for el in elements:
                shape = el.get('shape')
                if shape and 'placeholder' in shape and shape['placeholder'].get('type') == p_type:
                    return el
            return None

        def has_text_content(element: Optional[Dict[str, Any]]) -> bool:
            """True when the shape contains non-whitespace text."""
            if not element:
                return False
            shape = element.get('shape', {})
            text_elements = shape.get('text', {}).get('textElements', [])
            for text_element in text_elements:
                text_run = text_element.get('textRun', {})
                if text_run.get('content', '').strip():
                    return True
                auto_text = text_element.get('autoText', {})
                if auto_text.get('content', '').strip():
                    return True
            return False

        # 2. Handle Background Color
        if params.background_color:
            rgb = hex_to_rgb(params.background_color)
            requests.append({
                'updatePageProperties': {
                    'objectId': slide_id,
                    'pageProperties': {
                        'pageBackgroundFill': {
                            'solidFill': {
                                'color': {
                                    'rgbColor': rgb
                                }
                            }
                        }
                    },
                    'fields': 'pageBackgroundFill.solidFill.color'
                }
            })

        # 3. Handle Title and Body text
        title_element = find_placeholder(slide.get('pageElements', []), 'TITLE') or \
                        find_placeholder(slide.get('pageElements', []), 'CENTERED_TITLE')
        title_id = title_element.get('objectId') if title_element else None
        
        if params.title and title_id:
            if has_text_content(title_element):
                requests.append({'deleteText': {'objectId': title_id, 'textRange': {'type': 'ALL'}}})
            requests.append({'insertText': {'objectId': title_id, 'text': params.title}})
        
        body_element = find_placeholder(slide.get('pageElements', []), 'BODY') or \
                       find_placeholder(slide.get('pageElements', []), 'OBJECT')
        body_id = body_element.get('objectId') if body_element else None
        
        if params.body and body_id:
            if has_text_content(body_element):
                requests.append({'deleteText': {'objectId': body_id, 'textRange': {'type': 'ALL'}}})
            requests.append({'insertText': {'objectId': body_id, 'text': params.body}})

        # 4. Handle Text Style (Foreground Color)
        if params.text_color:
            rgb = hex_to_rgb(params.text_color)
            if title_id:
                requests.append({
                    'updateTextStyle': {
                        'objectId': title_id,
                        'style': {
                            'foregroundColor': {
                                'opaqueColor': {
                                    'rgbColor': rgb
                                }
                            }
                        },
                        'fields': 'foregroundColor'
                    }
                })
            if body_id:
                requests.append({
                    'updateTextStyle': {
                        'objectId': body_id,
                        'style': {
                            'foregroundColor': {
                                'opaqueColor': {
                                    'rgbColor': rgb
                                }
                            }
                        },
                        'fields': 'foregroundColor'
                    }
                })

        # 5. Handle Speaker Notes
        if params.speaker_notes:
            notes_page = slide.get('notesPage')
            if notes_page:
                notes_element = find_placeholder(notes_page.get('pageElements', []), 'BODY')
                notes_obj_id = notes_element.get('objectId') if notes_element else None
                if notes_obj_id:
                    if has_text_content(notes_element):
                        requests.append({'deleteText': {'objectId': notes_obj_id, 'textRange': {'type': 'ALL'}}})
                    requests.append({'insertText': {'objectId': notes_obj_id, 'text': params.speaker_notes}})

        if not requests:
            return "No updates performed. Check if placeholders exist on the slide."

        service.presentations().batchUpdate(
            presentationId=params.presentation_id,
            body={'requests': requests}
        ).execute()
        
        return f"Successfully updated slide {params.slide_index}"
    except Exception as e:
        return f"Error updating slide: {str(e)}"

@mcp.tool(name="slides_delete_slide")
async def delete_slide(params: DeleteSlideInput) -> str:
    """Deletes a slide at a specified 1-based index."""
    try:
        service = get_slides_service()
        presentation = service.presentations().get(presentationId=params.presentation_id).execute()
        slides = presentation.get('slides', [])
        
        if params.slide_index > len(slides):
            return f"Error: Slide index {params.slide_index} out of bounds."
        
        slide_id = slides[params.slide_index - 1].get('objectId')
        
        requests = [{'deleteObject': {'objectId': slide_id}}]
        service.presentations().batchUpdate(
            presentationId=params.presentation_id,
            body={'requests': requests}
        ).execute()
        
        return f"Successfully deleted slide {params.slide_index}"
    except Exception as e:
        return f"Error deleting slide: {str(e)}"

@mcp.tool(name="slides_get_presentation")
async def get_presentation(presentation_id: str) -> str:
    """Returns information about a presentation and its slides."""
    try:
        service = get_slides_service()
        presentation = service.presentations().get(presentationId=presentation_id).execute()
        
        summary = {
            "title": presentation.get('title'),
            "presentationId": presentation.get('presentationId'),
            "slideCount": len(presentation.get('slides', [])),
            "slides": []
        }
        
        for i, slide in enumerate(presentation.get('slides', []), 1):
            summary["slides"].append({
                "index": i,
                "objectId": slide.get('objectId')
            })
            
        return json.dumps(summary, indent=2)
    except Exception as e:
        return f"Error getting presentation: {str(e)}"

if __name__ == "__main__":
    mcp.run()

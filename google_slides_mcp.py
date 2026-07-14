import os
import json
import logging
import sys
from contextlib import redirect_stdout
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
            # We redirect stdout to stderr to ensure the "Please visit this URL" message
            # doesn't break the MCP protocol (which uses stdout for JSON-RPC).
            with redirect_stdout(sys.stderr):
                try:
                    # Try to run local server (default)
                    creds = flow.run_local_server(port=0, open_browser=True)
                except Exception as e:
                    logger.warning(f"Could not open browser for authentication: {e}")
                    logger.info("Falling back to manual authentication URL...")
                    # Note: run_local_server with open_browser=False will print the URL to stdout
                    creds = flow.run_local_server(port=0, open_browser=False)

                
        # Save the credentials for the next run
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            logger.info(f"Saved new token to {token_path}")
            
    return creds

def get_slides_service():
    creds = get_credentials()
    return build('slides', 'v1', credentials=creds)

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

class DeleteSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based index of the slide to delete.", ge=1)

class SpeakerNotesExperimentInput(BaseModel):
    title: str = Field(
        "Speaker Notes Experiment",
        description="Title for the generated test presentation.",
    )
    slides_count: int = Field(
        5,
        description="How many similar slides to create for strategy testing.",
        ge=2,
        le=20,
    )
    base_slide_layout: str = Field(
        "TITLE_AND_BODY",
        description="Layout to use for generated test slides.",
    )
    debug: bool = Field(
        False,
        description="Include verbose diagnostics with before/after notes internals and request payloads.",
    )

# --- Helpers ---

def find_placeholder(elements, p_type):
    for el in elements:
        shape = el.get('shape')
        if shape and 'placeholder' in shape and shape['placeholder'].get('type') == p_type:
            return el.get('objectId')
    return None

def find_placeholder_element(elements: List[Dict[str, Any]], p_type: str) -> Optional[Dict[str, Any]]:
    for el in elements:
        shape = el.get('shape')
        if shape and 'placeholder' in shape and shape['placeholder'].get('type') == p_type:
            return el
    return None

def has_text_content(element: Optional[Dict[str, Any]]) -> bool:
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

def find_element_by_object_id(elements: List[Dict[str, Any]], object_id: str) -> Optional[Dict[str, Any]]:
    for el in elements:
        if el.get('objectId') == object_id:
            return el
    return None

def extract_notes_text(slide: Dict[str, Any]) -> str:
    notes_page = slide.get('notesPage') or {}
    notes_obj_id = notes_page.get('notesProperties', {}).get('speakerNotesObjectId')
    notes_element = None
    if notes_obj_id:
        notes_element = find_element_by_object_id(notes_page.get('pageElements', []), notes_obj_id)
    if not notes_element:
        notes_element = find_placeholder_element(notes_page.get('pageElements', []), 'BODY')
    if not notes_element:
        return ""

    text_chunks: List[str] = []
    text_elements = notes_element.get('shape', {}).get('text', {}).get('textElements', [])
    for text_element in text_elements:
        text_run = text_element.get('textRun', {})
        if 'content' in text_run:
            text_chunks.append(text_run['content'])
        auto_text = text_element.get('autoText', {})
        if 'content' in auto_text:
            text_chunks.append(auto_text['content'])
    return ''.join(text_chunks).strip()

def fetch_notes_page(
    service: Any,
    presentation_id: str,
    slide: Dict[str, Any],
) -> Dict[str, Any]:
    notes_page_from_slide = slide.get('notesPage') or slide.get('slideProperties', {}).get('notesPage') or {}
    notes_page_object_id = notes_page_from_slide.get('objectId')
    if notes_page_object_id:
        try:
            return service.presentations().pages().get(
                presentationId=presentation_id,
                pageObjectId=notes_page_object_id,
            ).execute()
        except Exception as exc:
            logger.warning("Failed to fetch notes page %s: %s", notes_page_object_id, exc)
    return notes_page_from_slide

def resolve_notes_targets(
    service: Any,
    presentation_id: str,
    slide: Dict[str, Any],
) -> Dict[str, Any]:
    notes_page = fetch_notes_page(service, presentation_id, slide)
    notes_props = notes_page.get('notesProperties', {})
    speaker_notes_object_id = notes_props.get('speakerNotesObjectId')
    page_elements = notes_page.get('pageElements', [])
    body_element = find_placeholder_element(page_elements, 'BODY')
    body_object_id = body_element.get('objectId') if body_element else None
    speaker_notes_element = (
        find_element_by_object_id(page_elements, speaker_notes_object_id)
        if speaker_notes_object_id else None
    )

    return {
        "notesPage": notes_page,
        "speakerNotesObjectId": speaker_notes_object_id,
        "bodyPlaceholderObjectId": body_object_id,
        "speakerNotesElement": speaker_notes_element,
        "bodyPlaceholderElement": body_element,
    }

def summarize_notes_page(
    service: Any,
    presentation_id: str,
    slide: Dict[str, Any],
) -> Dict[str, Any]:
    resolved = resolve_notes_targets(service, presentation_id, slide)
    notes_page = resolved["notesPage"]
    page_elements = notes_page.get('pageElements', [])
    speaker_notes_element = resolved["speakerNotesElement"]
    body_element = resolved["bodyPlaceholderElement"]
    return {
        "speakerNotesObjectId": resolved["speakerNotesObjectId"],
        "bodyPlaceholderObjectId": resolved["bodyPlaceholderObjectId"],
        "notesPageElementCount": len(page_elements),
        "speakerNotesShapeFound": speaker_notes_element is not None,
        "bodyPlaceholderFound": body_element is not None,
        "extractedNotesText": extract_notes_text({"notesPage": notes_page}),
        "notesPageTextElements": (
            speaker_notes_element.get('shape', {}).get('text', {}).get('textElements', [])
            if speaker_notes_element else []
        ),
    }

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
    """Updates title, body, or speaker notes of a slide by its 1-based index."""
    try:
        service = get_slides_service()
        # 1. Get presentation to find the slide objectId at the given index
        presentation = service.presentations().get(presentationId=params.presentation_id).execute()
        slides = presentation.get('slides', [])
        
        if params.slide_index > len(slides):
            return f"Error: Slide index {params.slide_index} out of bounds (Total slides: {len(slides)})"
        
        slide = slides[params.slide_index - 1]
        requests = []

        # Helper to find placeholder
        def find_placeholder(elements, p_type):
            for el in elements:
                shape = el.get('shape')
                if shape and 'placeholder' in shape and shape['placeholder'].get('type') == p_type:
                    return el
            return None
        
        def find_element_by_object_id(elements, object_id):
            for el in elements:
                if el.get('objectId') == object_id:
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

        # 2. Handle Title and Body text
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

        # 3. Handle Speaker Notes
        if params.speaker_notes:
            resolved_notes = resolve_notes_targets(service, params.presentation_id, slide)
            notes_obj_id = resolved_notes["speakerNotesObjectId"] or resolved_notes["bodyPlaceholderObjectId"]
            notes_element = resolved_notes["speakerNotesElement"] or resolved_notes["bodyPlaceholderElement"]
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

@mcp.tool(name="slides_speaker_notes_experiment")
async def speaker_notes_experiment(params: SpeakerNotesExperimentInput) -> str:
    """Creates similar slides and tests multiple speaker-notes write strategies."""
    try:
        service = get_slides_service()

        presentation = service.presentations().create(body={'title': params.title}).execute()
        presentation_id = presentation.get('presentationId')

        create_requests: List[Dict[str, Any]] = []
        for _ in range(params.slides_count):
            create_requests.append(
                {
                    'createSlide': {
                        'slideLayoutReference': {'predefinedLayout': params.base_slide_layout}
                    }
                }
            )

        create_response = service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': create_requests}
        ).execute()
        created_slide_ids = [
            reply.get('createSlide', {}).get('objectId')
            for reply in create_response.get('replies', [])
            if reply.get('createSlide', {}).get('objectId')
        ]

        def get_slide_by_id(deck_data: Dict[str, Any], target_slide_id: str) -> Optional[Dict[str, Any]]:
            for candidate in deck_data.get('slides', []):
                if candidate.get('objectId') == target_slide_id:
                    return candidate
            return None

        approaches = [
            "notes_properties_insert_only",
            "notes_properties_delete_then_insert",
            "notes_body_placeholder_insert_only",
            "notes_body_placeholder_delete_then_insert",
            "both_paths_with_fallback",
        ]

        results: List[Dict[str, Any]] = []
        for idx, slide_id in enumerate(created_slide_ids):
            deck_before = service.presentations().get(presentationId=presentation_id).execute()
            slide = get_slide_by_id(deck_before, slide_id) or {}
            approach = approaches[idx % len(approaches)]
            notes_text = f"Speaker notes strategy: {approach} (slide {idx + 1})"

            title_id = find_placeholder(slide.get('pageElements', []), 'TITLE') or \
                       find_placeholder(slide.get('pageElements', []), 'CENTERED_TITLE')
            body_id = find_placeholder(slide.get('pageElements', []), 'BODY') or \
                      find_placeholder(slide.get('pageElements', []), 'OBJECT')

            prep_requests: List[Dict[str, Any]] = []
            if title_id:
                prep_requests.append({'insertText': {'objectId': title_id, 'text': f"Notes Test {idx + 1}"}})
            if body_id:
                prep_requests.append({'insertText': {'objectId': body_id, 'text': "Control body content"}})
            if prep_requests:
                service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={'requests': prep_requests}
                ).execute()

            refreshed_deck = service.presentations().get(presentationId=presentation_id).execute()
            refreshed_slide = get_slide_by_id(refreshed_deck, slide_id) or {}
            resolved_notes = resolve_notes_targets(service, presentation_id, refreshed_slide)
            notes_obj_id = resolved_notes["speakerNotesObjectId"]
            notes_element = resolved_notes["speakerNotesElement"]
            body_notes_element = resolved_notes["bodyPlaceholderElement"]

            write_requests: List[Dict[str, Any]] = []
            target_ids: List[str] = []
            if approach in ("notes_properties_insert_only", "notes_properties_delete_then_insert", "both_paths_with_fallback") and notes_obj_id:
                target_ids.append(notes_obj_id)
            if approach in ("notes_body_placeholder_insert_only", "notes_body_placeholder_delete_then_insert", "both_paths_with_fallback") and body_notes_element:
                body_notes_id = body_notes_element.get('objectId')
                if body_notes_id:
                    target_ids.append(body_notes_id)
            target_ids = list(dict.fromkeys(target_ids))

            for target_id in target_ids:
                should_delete = approach in (
                    "notes_properties_delete_then_insert",
                    "notes_body_placeholder_delete_then_insert",
                    "both_paths_with_fallback",
                )
                target_element = notes_element if target_id == notes_obj_id else body_notes_element
                if should_delete and has_text_content(target_element):
                    write_requests.append({'deleteText': {'objectId': target_id, 'textRange': {'type': 'ALL'}}})
                write_requests.append({'insertText': {'objectId': target_id, 'text': notes_text}})

            if not write_requests:
                results.append(
                    {
                        "slideId": slide_id,
                        "approach": approach,
                        "status": "skipped",
                        "reason": "No notes shape target found",
                        "before": summarize_notes_page(service, presentation_id, refreshed_slide) if params.debug else None,
                    }
                )
                continue

            service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': write_requests}
            ).execute()

            verify_deck = service.presentations().get(presentationId=presentation_id).execute()
            verify_slide = get_slide_by_id(verify_deck, slide_id) or {}
            verify_summary = summarize_notes_page(service, presentation_id, verify_slide)
            read_back = verify_summary.get("extractedNotesText", "")
            slide_result: Dict[str, Any] = {
                "slideId": slide_id,
                "approach": approach,
                "expectedNotes": notes_text,
                "readBackNotes": read_back,
                "matches": read_back == notes_text,
            }
            if params.debug:
                slide_result["before"] = summarize_notes_page(service, presentation_id, refreshed_slide)
                slide_result["writeRequests"] = write_requests
                slide_result["after"] = verify_summary
            results.append(slide_result)

        return json.dumps(
            {
                "presentationId": presentation_id,
                "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit",
                "slidesCreated": len(created_slide_ids),
                "results": results,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error running speaker notes experiment: {str(e)}"

if __name__ == "__main__":
    mcp.run()

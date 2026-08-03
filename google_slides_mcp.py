import os
import json
import logging
import sys
import requests
import uuid
from copy import deepcopy
from contextlib import redirect_stdout
from typing import Annotated, Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
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

class ApplyDarkThemeInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    background_hex: str = Field("#0B1020", description="Slide background color in #RRGGBB format.")
    title_hex: str = Field("#F8FAFC", description="Title text color in #RRGGBB format.")
    body_hex: str = Field("#CBD5E1", description="Body text color in #RRGGBB format.")
    font_family: str = Field("Aptos", description="Font family applied to slide text.")

class ExportThumbnailsInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    output_dir: str = Field(..., description="Local directory for exported PNG thumbnails.")

class ExportSlideThumbnailInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based index of the slide to export.", ge=1)
    output_path: str = Field(..., description="Local path for the exported PNG file.")

class VisualElementInput(BaseModel):
    x: float = Field(..., description="Left position in points.")
    y: float = Field(..., description="Top position in points.")
    width: float = Field(..., description="Width in points.", gt=0)
    height: float = Field(..., description="Height in points.", gt=0)
    text: str = Field("", description="Text inside the element.")
    shape_type: str = Field("TEXT_BOX", description="Google Slides shape type.")
    fill_hex: Optional[str] = Field(None, description="Fill color in #RRGGBB format; omit for transparent.")
    fill_alpha: float = Field(1.0, description="Fill opacity from 0 to 1.", ge=0, le=1)
    border_hex: Optional[str] = Field(None, description="Border color in #RRGGBB format; omit for no border.")
    border_alpha: float = Field(1.0, description="Border opacity from 0 to 1.", ge=0, le=1)
    border_weight: float = Field(1.0, description="Border weight in points.", ge=0)
    text_hex: str = Field("#FFFFFF", description="Text color in #RRGGBB format.")
    font_family: str = Field("Arial", description="Font family.")
    font_size: float = Field(18, description="Font size in points.", gt=0)
    bold: bool = Field(False, description="Whether text is bold.")
    alignment: str = Field("START", description="Paragraph alignment: START, CENTER, END.")
    valign: str = Field("MIDDLE", description="Vertical alignment: TOP, MIDDLE, BOTTOM.")

class ComposeSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based slide index.", ge=1)
    background_hex: str = Field("#0B1020", description="Slide background in #RRGGBB format.")
    title_hex: str = Field("#F8FAFC", description="Existing title color in #RRGGBB format.")
    accent_hex: str = Field("#49D3FF", description="Accent color in #RRGGBB format.")
    clear_body: bool = Field(True, description="Remove text from the existing body placeholder.")
    clear_title: bool = Field(False, description="Remove text from the existing title placeholder.")
    elements: List[VisualElementInput] = Field(default_factory=list, description="Native slide elements to create.")

class DeleteSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based index of the slide to delete.", ge=1)

class DuplicateSlideInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_index: int = Field(..., description="1-based index of the slide to duplicate.", ge=1)

class RearrangeSlidesInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    slide_positions: Dict[int, int] = Field(
        ...,
        description=(
            "Mapping of current 1-based slide numbers to their new 1-based positions. "
            "For example, {\"1\": 3, \"3\": 1} swaps slides 1 and 3. "
            "Unspecified slides keep their relative order in the remaining positions."
        ),
        min_length=1,
    )

class BatchUpdateInput(BaseModel):
    presentation_id: str = Field(..., description="The ID of the presentation.")
    requests: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        description=(
            "Raw Google Slides presentations.batchUpdate requests. For "
            "updateTextStyle.style.foregroundColor, use an OptionalColor wrapper: "
            "{\"opaqueColor\": {\"rgbColor\": {\"red\": 0, \"green\": 0.44, \"blue\": 0.75}}}. "
            "A #RRGGBB foregroundColor string is also accepted and normalized to that wrapper."
        ),
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

def summarize_page_element(element: Dict[str, Any]) -> Dict[str, Any]:
    """Return the stable identity and layout data needed for surgical edits."""
    element_types = (
        'shape', 'image', 'table', 'line', 'video', 'wordArt',
        'sheetsChart', 'elementGroup',
    )
    element_type = next((name for name in element_types if name in element), 'unknown')
    summary: Dict[str, Any] = {
        "objectId": element.get('objectId'),
        "type": element_type,
        "size": element.get('size'),
        "transform": element.get('transform'),
    }

    if element.get('title') is not None:
        summary["title"] = element.get('title')
    if element.get('description') is not None:
        summary["description"] = element.get('description')

    shape = element.get('shape')
    if shape:
        summary["shapeType"] = shape.get('shapeType')
        placeholder = shape.get('placeholder')
        if placeholder:
            summary["placeholderType"] = placeholder.get('type')
        text = ''.join(
            text_element.get('textRun', {}).get('content', '')
            or text_element.get('autoText', {}).get('content', '')
            for text_element in shape.get('text', {}).get('textElements', [])
        ).rstrip('\n')
        if text:
            summary["text"] = text

    table = element.get('table')
    if table:
        summary["rows"] = table.get('rows')
        summary["columns"] = table.get('columns')

    return summary

def hex_to_rgb(hex_color: str) -> Dict[str, float]:
    value = hex_color.strip().lstrip('#')
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {hex_color!r}")
    return {
        "red": int(value[0:2], 16) / 255.0,
        "green": int(value[2:4], 16) / 255.0,
        "blue": int(value[4:6], 16) / 255.0,
    }

def normalize_text_style_foreground_colors(
    batch_requests: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Normalize shorthand text colors and reject the invalid direct Color shape.

    TextStyle.foregroundColor is an OptionalColor, unlike shape fills whose
    solidFill.color field is a Color. Keep all other raw Google API requests
    untouched so callers can use the full batchUpdate surface.
    """
    normalized_requests = deepcopy(batch_requests)
    for request_index, request in enumerate(normalized_requests):
        update_text_style = request.get("updateTextStyle")
        if not isinstance(update_text_style, dict):
            continue
        style = update_text_style.get("style")
        if not isinstance(style, dict) or "foregroundColor" not in style:
            continue

        foreground_color = style["foregroundColor"]
        if isinstance(foreground_color, str):
            style["foregroundColor"] = {
                "opaqueColor": {"rgbColor": hex_to_rgb(foreground_color)}
            }
        elif isinstance(foreground_color, dict) and "rgbColor" in foreground_color:
            raise ValueError(
                f"requests[{request_index}].updateTextStyle.style.foregroundColor "
                "must be an OptionalColor wrapper: "
                "{\"opaqueColor\": {\"rgbColor\": {...}}}, not {\"rgbColor\": {...}}."
            )
    return normalized_requests

def export_thumbnail_file(
    service: Any,
    presentation_id: str,
    slide_object_id: str,
    output_path: str,
) -> str:
    """Download one Google Slides page thumbnail to a local PNG file."""
    thumbnail = service.presentations().pages().getThumbnail(
        presentationId=presentation_id,
        pageObjectId=slide_object_id,
        thumbnailProperties_thumbnailSize='LARGE',
        thumbnailProperties_mimeType='PNG',
    ).execute()
    response = requests.get(thumbnail['contentUrl'], timeout=30)
    response.raise_for_status()

    absolute_output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(absolute_output_path), exist_ok=True)
    with open(absolute_output_path, 'wb') as output_file:
        output_file.write(response.content)
    return output_path

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

@mcp.tool(name="create_presentation", 
    annotations=ToolAnnotations(
        title="Create Google Slides Presentation",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ))
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

@mcp.tool(name="add_slide", 
    annotations=ToolAnnotations(
        title="Create Google Slides presentation slide",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ))
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

@mcp.tool(name="duplicate_slide",
    annotations=ToolAnnotations(
        title="Duplicate Google Slides presentation slide",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ))
async def duplicate_slide(params: DuplicateSlideInput) -> str:
    """Duplicates a slide selected by its 1-based index."""
    try:
        service = get_slides_service()
        presentation = service.presentations().get(
            presentationId=params.presentation_id
        ).execute()
        slides = presentation.get('slides', [])

        if params.slide_index > len(slides):
            return (
                f"Error: Slide index {params.slide_index} out of bounds "
                f"(Total slides: {len(slides)})"
            )

        source_slide_id = slides[params.slide_index - 1].get('objectId')
        response = service.presentations().batchUpdate(
            presentationId=params.presentation_id,
            body={
                'requests': [
                    {'duplicateObject': {'objectId': source_slide_id}}
                ]
            },
        ).execute()
        duplicated_slide_id = (
            response.get('replies', [{}])[0]
            .get('duplicateObject', {})
            .get('objectId')
        )

        return json.dumps({
            "sourceSlideIndex": params.slide_index,
            "sourceSlideId": source_slide_id,
            "duplicatedSlideId": duplicated_slide_id,
        }, indent=2)
    except Exception as e:
        return f"Error duplicating slide: {str(e)}"

@mcp.tool(name="rearrange_slides",
    annotations=ToolAnnotations(
        title="Rearrange Google Slides presentation slides",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
async def rearrange_slides(
    presentation_id: Annotated[str, Field(description="The ID of the presentation.")],
    slide_positions: Annotated[
        Dict[int, int],
        Field(
            description=(
                "Object mapping current 1-based slide numbers to new 1-based positions. "
                "Example: {\"1\": 3, \"3\": 1}. Unspecified slides retain their relative order."
            ),
            min_length=1,
        ),
    ],
) -> str:
    """Moves slides to requested 1-based positions while preserving unspecified slide order."""
    params = RearrangeSlidesInput(
        presentation_id=presentation_id,
        slide_positions=slide_positions,
    )
    try:
        service = get_slides_service()
        presentation = service.presentations().get(
            presentationId=params.presentation_id
        ).execute()
        slides = presentation.get('slides', [])
        slide_count = len(slides)
        positions = params.slide_positions

        invalid_sources = sorted(index for index in positions if index < 1 or index > slide_count)
        if invalid_sources:
            return (
                f"Error: Slide numbers out of bounds (valid range: 1-{slide_count}): "
                f"{invalid_sources}"
            )

        invalid_destinations = sorted(
            position for position in positions.values()
            if position < 1 or position > slide_count
        )
        if invalid_destinations:
            return (
                f"Error: New positions out of bounds (valid range: 1-{slide_count}): "
                f"{invalid_destinations}"
            )

        destination_values = list(positions.values())
        if len(destination_values) != len(set(destination_values)):
            return "Error: Each requested new position must belong to exactly one slide."

        current_order = [slide.get('objectId') for slide in slides]
        desired_order: List[Optional[str]] = [None] * slide_count
        moved_ids = set()
        for source_index, destination_index in positions.items():
            slide_id = current_order[source_index - 1]
            desired_order[destination_index - 1] = slide_id
            moved_ids.add(slide_id)

        remaining_ids = iter(slide_id for slide_id in current_order if slide_id not in moved_ids)
        desired_order = [slide_id if slide_id is not None else next(remaining_ids) for slide_id in desired_order]

        requests: List[Dict[str, Any]] = []
        for target_index, slide_id in enumerate(desired_order):
            current_index = current_order.index(slide_id)
            if current_index == target_index:
                continue
            insertion_index = target_index + (1 if current_index < target_index else 0)
            requests.append({
                'updateSlidesPosition': {
                    'slideObjectIds': [slide_id],
                    'insertionIndex': insertion_index,
                }
            })
            current_order.pop(current_index)
            current_order.insert(target_index, slide_id)

        if requests:
            service.presentations().batchUpdate(
                presentationId=params.presentation_id,
                body={'requests': requests},
            ).execute()

        return json.dumps({
            "slideCount": slide_count,
            "requestedPositions": positions,
            "finalOrder": [slide_id for slide_id in desired_order],
            "movedSlideCount": len(requests),
        }, indent=2)
    except Exception as e:
        return f"Error rearranging slides: {str(e)}"

@mcp.tool(name="batch_update",
    annotations=ToolAnnotations(
        title="Run raw Google Slides batch update requests",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ))
async def batch_update(params: BatchUpdateInput) -> str:
    """Runs raw presentations.batchUpdate requests with safe text-color validation.

    TextStyle foregroundColor is an OptionalColor, so use
    {"opaqueColor": {"rgbColor": {...}}}. Shape fills remain raw Google API
    Color values, for example shapeBackgroundFill.solidFill.color.rgbColor.
    """
    try:
        normalized_requests = normalize_text_style_foreground_colors(params.requests)
    except ValueError as exc:
        return f"Error validating batch update: {exc}"

    try:
        response = get_slides_service().presentations().batchUpdate(
            presentationId=params.presentation_id,
            body={"requests": normalized_requests},
        ).execute()
        return json.dumps(response, indent=2)
    except Exception as exc:
        return f"Error running batch update: {str(exc)}"

@mcp.tool(name="update_slide", 
    annotations=ToolAnnotations(
        title="Update Google Slides presentation slide",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
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
                       find_placeholder(slide.get('pageElements', []), 'OBJECT') or \
                       find_placeholder(slide.get('pageElements', []), 'SUBTITLE')
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

@mcp.tool(name="apply_dark_theme", 
    annotations=ToolAnnotations(
        title="Apply Dark Theme to Google Slides Presentation",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
async def apply_dark_theme(params: ApplyDarkThemeInput) -> str:
    """Applies a consistent dark background and readable typography to every slide."""
    try:
        service = get_slides_service()
        presentation = service.presentations().get(
            presentationId=params.presentation_id
        ).execute()
        requests: List[Dict[str, Any]] = []
        background_rgb = hex_to_rgb(params.background_hex)
        title_rgb = hex_to_rgb(params.title_hex)
        body_rgb = hex_to_rgb(params.body_hex)

        for slide_number, slide in enumerate(presentation.get('slides', []), 1):
            requests.append({
                'updatePageProperties': {
                    'objectId': slide.get('objectId'),
                    'pageProperties': {
                        'pageBackgroundFill': {
                            'solidFill': {
                                'color': {'rgbColor': background_rgb},
                                'alpha': 1,
                            },
                            'propertyState': 'RENDERED',
                        }
                    },
                    'fields': 'pageBackgroundFill',
                }
            })

            for element in slide.get('pageElements', []):
                shape = element.get('shape') or {}
                placeholder_type = shape.get('placeholder', {}).get('type')
                if not placeholder_type or not has_text_content(element):
                    continue

                is_title = placeholder_type in {'TITLE', 'CENTERED_TITLE'}
                is_subtitle = placeholder_type == 'SUBTITLE'
                if slide_number == 1 and is_title:
                    font_size = 50
                elif is_title:
                    font_size = 36
                elif is_subtitle:
                    font_size = 24
                else:
                    font_size = 20

                color = title_rgb if is_title else body_rgb
                requests.append({
                    'updateTextStyle': {
                        'objectId': element.get('objectId'),
                        'textRange': {'type': 'ALL'},
                        'style': {
                            'foregroundColor': {
                                'opaqueColor': {'rgbColor': color}
                            },
                            'fontFamily': params.font_family,
                            'fontSize': {'magnitude': font_size, 'unit': 'PT'},
                            'bold': bool(is_title),
                        },
                        'fields': 'foregroundColor,fontFamily,fontSize,bold',
                    }
                })

        if requests:
            service.presentations().batchUpdate(
                presentationId=params.presentation_id,
                body={'requests': requests},
            ).execute()
        return f"Applied dark theme to {len(presentation.get('slides', []))} slides"
    except Exception as e:
        return f"Error applying dark theme: {str(e)}"

@mcp.tool(name="export_thumbnails", 
    annotations=ToolAnnotations(
        title="Exports a PNG thumbnail for every slide to a local directory for visual QA.",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
async def export_thumbnails(params: ExportThumbnailsInput) -> str:
    """Exports a PNG thumbnail for every slide to a local directory for visual QA."""
    try:
        service = get_slides_service()
        presentation = service.presentations().get(
            presentationId=params.presentation_id
        ).execute()
        os.makedirs(params.output_dir, exist_ok=True)
        exported: List[str] = []

        for number, slide in enumerate(presentation.get('slides', []), 1):
            output_path = os.path.join(params.output_dir, f"slide-{number:02d}.png")
            exported.append(export_thumbnail_file(
                service,
                params.presentation_id,
                slide.get('objectId'),
                output_path,
            ))

        return json.dumps({"count": len(exported), "files": exported}, indent=2)
    except Exception as e:
        return f"Error exporting thumbnails: {str(e)}"

@mcp.tool(name="export_slide_thumbnail",
    annotations=ToolAnnotations(
        title="Export one Google Slides page as a PNG thumbnail",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
async def export_slide_thumbnail(
    presentation_id: Annotated[str, Field(description="The ID of the presentation.")],
    slide_index: Annotated[int, Field(description="1-based index of the slide to export.", ge=1)],
    output_path: Annotated[str, Field(description="Local path for the exported PNG file.")],
) -> str:
    """Exports one slide selected by its 1-based index to a local PNG file."""
    params = ExportSlideThumbnailInput(
        presentation_id=presentation_id,
        slide_index=slide_index,
        output_path=output_path,
    )
    try:
        service = get_slides_service()
        presentation = service.presentations().get(
            presentationId=params.presentation_id
        ).execute()
        slides = presentation.get('slides', [])
        if params.slide_index > len(slides):
            return (
                f"Error: Slide index {params.slide_index} out of bounds "
                f"(valid range: 1-{len(slides)})."
            )

        slide_object_id = slides[params.slide_index - 1].get('objectId')
        exported_file = export_thumbnail_file(
            service,
            params.presentation_id,
            slide_object_id,
            params.output_path,
        )
        return json.dumps({
            "count": 1,
            "slideIndex": params.slide_index,
            "slideObjectId": slide_object_id,
            "file": exported_file,
        }, indent=2)
    except Exception as e:
        return f"Error exporting slide thumbnail: {str(e)}"

@mcp.tool(name="compose_slide", 
    annotations=ToolAnnotations(
        title="Compose Google Slides presentation slide elements",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
async def compose_slide(
    presentation_id: Annotated[str, Field(description="The ID of the presentation.")],
    slide_index: Annotated[int, Field(description="1-based slide index.", ge=1)],
    background_hex: Annotated[
        str, Field(description="Slide background in #RRGGBB format.")
    ] = "#0B1020",
    title_hex: Annotated[
        str, Field(description="Existing title color in #RRGGBB format.")
    ] = "#F8FAFC",
    accent_hex: Annotated[
        str, Field(description="Accent color in #RRGGBB format.")
    ] = "#49D3FF",
    clear_body: Annotated[
        bool, Field(description="Remove text from the existing body placeholder.")
    ] = True,
    clear_title: Annotated[
        bool, Field(description="Remove text from the existing title placeholder.")
    ] = False,
    elements: Annotated[
        List[VisualElementInput],
        Field(
            description=(
                "Native slide elements to create. Each array item must include x, y, "
                "width, and height; all styling fields are optional."
            )
        ),
    ] = [],
) -> str:
    """Clears the body and composes a slide from positioned native text/shape elements."""
    params = ComposeSlideInput(
        presentation_id=presentation_id,
        slide_index=slide_index,
        background_hex=background_hex,
        title_hex=title_hex,
        accent_hex=accent_hex,
        clear_body=clear_body,
        clear_title=clear_title,
        elements=elements,
    )
    try:
        service = get_slides_service()
        presentation = service.presentations().get(
            presentationId=params.presentation_id
        ).execute()
        slides = presentation.get('slides', [])
        if params.slide_index > len(slides):
            return f"Error: Slide index {params.slide_index} out of bounds."

        slide = slides[params.slide_index - 1]
        slide_id = slide.get('objectId')
        requests: List[Dict[str, Any]] = []

        # Make the operation repeatable by removing only elements created by this tool.
        for element in slide.get('pageElements', []):
            object_id = element.get('objectId', '')
            if object_id.startswith('qa_vis_'):
                requests.append({'deleteObject': {'objectId': object_id}})

        if params.clear_body:
            body_element = find_placeholder_element(slide.get('pageElements', []), 'BODY') or \
                           find_placeholder_element(slide.get('pageElements', []), 'OBJECT') or \
                           find_placeholder_element(slide.get('pageElements', []), 'SUBTITLE')
            if body_element and has_text_content(body_element):
                requests.append({
                    'deleteText': {
                        'objectId': body_element.get('objectId'),
                        'textRange': {'type': 'ALL'},
                    }
                })

        title_element = find_placeholder_element(slide.get('pageElements', []), 'TITLE') or \
                        find_placeholder_element(slide.get('pageElements', []), 'CENTERED_TITLE')
        if title_element and has_text_content(title_element) and params.clear_title:
            requests.append({
                'deleteText': {
                    'objectId': title_element.get('objectId'),
                    'textRange': {'type': 'ALL'},
                }
            })
        elif title_element and has_text_content(title_element):
            requests.append({
                'updateTextStyle': {
                    'objectId': title_element.get('objectId'),
                    'textRange': {'type': 'ALL'},
                    'style': {
                        'foregroundColor': {
                            'opaqueColor': {'rgbColor': hex_to_rgb(params.title_hex)}
                        },
                        'fontFamily': 'Arial',
                        'fontSize': {
                            'magnitude': 50 if params.slide_index == 1 else 36,
                            'unit': 'PT',
                        },
                        'bold': True,
                    },
                    'fields': 'foregroundColor,fontFamily,fontSize,bold',
                }
            })

        requests.append({
            'updatePageProperties': {
                'objectId': slide_id,
                'pageProperties': {
                    'pageBackgroundFill': {
                        'solidFill': {
                            'color': {'rgbColor': hex_to_rgb(params.background_hex)},
                            'alpha': 1,
                        },
                        'propertyState': 'RENDERED',
                    }
                },
                'fields': 'pageBackgroundFill',
            }
        })

        # A consistent accent rule and slide number create deck-level rhythm.
        standard_elements = [
            VisualElementInput(
                x=50, y=77, width=72, height=4, shape_type='RECTANGLE',
                fill_hex=params.accent_hex, border_hex=params.accent_hex,
            ),
            VisualElementInput(
                x=672, y=378, width=28, height=16,
                text=f"{params.slide_index:02d}", font_size=9,
                text_hex=params.accent_hex, alignment='END', valign='MIDDLE',
            ),
        ]

        for element_number, element in enumerate(standard_elements + params.elements, 1):
            object_id = f"qa_vis_{params.slide_index}_{element_number}_{uuid.uuid4().hex[:8]}"
            requests.append({
                'createShape': {
                    'objectId': object_id,
                    'shapeType': element.shape_type,
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': element.width, 'unit': 'PT'},
                            'height': {'magnitude': element.height, 'unit': 'PT'},
                        },
                        'transform': {
                            'scaleX': 1,
                            'scaleY': 1,
                            'translateX': element.x,
                            'translateY': element.y,
                            'unit': 'PT',
                        },
                    },
                }
            })

            shape_properties: Dict[str, Any] = {
                'contentAlignment': element.valign,
            }
            fields = ['contentAlignment']
            if element.fill_hex:
                shape_properties['shapeBackgroundFill'] = {
                    'solidFill': {
                        'color': {'rgbColor': hex_to_rgb(element.fill_hex)},
                        'alpha': element.fill_alpha,
                    },
                    'propertyState': 'RENDERED',
                }
            else:
                shape_properties['shapeBackgroundFill'] = {'propertyState': 'NOT_RENDERED'}
            fields.append('shapeBackgroundFill')

            if element.border_hex:
                shape_properties['outline'] = {
                    'outlineFill': {
                        'solidFill': {
                            'color': {'rgbColor': hex_to_rgb(element.border_hex)},
                            'alpha': element.border_alpha,
                        }
                    },
                    'weight': {'magnitude': element.border_weight, 'unit': 'PT'},
                    'dashStyle': 'SOLID',
                    'propertyState': 'RENDERED',
                }
            else:
                shape_properties['outline'] = {'propertyState': 'NOT_RENDERED'}
            fields.append('outline')

            requests.append({
                'updateShapeProperties': {
                    'objectId': object_id,
                    'shapeProperties': shape_properties,
                    'fields': ','.join(fields),
                }
            })

            if element.text:
                requests.append({'insertText': {'objectId': object_id, 'text': element.text}})
                requests.append({
                    'updateTextStyle': {
                        'objectId': object_id,
                        'textRange': {'type': 'ALL'},
                        'style': {
                            'foregroundColor': {
                                'opaqueColor': {'rgbColor': hex_to_rgb(element.text_hex)}
                            },
                            'fontFamily': element.font_family,
                            'fontSize': {'magnitude': element.font_size, 'unit': 'PT'},
                            'bold': element.bold,
                        },
                        'fields': 'foregroundColor,fontFamily,fontSize,bold',
                    }
                })
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': object_id,
                        'textRange': {'type': 'ALL'},
                        'style': {'alignment': element.alignment},
                        'fields': 'alignment',
                    }
                })

        if requests:
            service.presentations().batchUpdate(
                presentationId=params.presentation_id,
                body={'requests': requests},
            ).execute()
        return f"Composed slide {params.slide_index} with {len(params.elements)} custom elements"
    except Exception as e:
        return f"Error composing slide: {str(e)}"

@mcp.tool(name="delete_slide")
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

@mcp.tool(name="get_presentation", 
    annotations=ToolAnnotations(
        title="Get Google Slides Presentation Information",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
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

@mcp.tool(name="get_slide_elements",
    annotations=ToolAnnotations(
        title="Get Google Slides page elements",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ))
async def get_slide_elements(
    presentation_id: Annotated[str, Field(description="The ID of the presentation.")],
    slide_index: Annotated[int, Field(description="1-based slide index.", ge=1)],
) -> str:
    """Returns object IDs, types, text, sizes, and transforms for one slide."""
    try:
        presentation = get_slides_service().presentations().get(
            presentationId=presentation_id
        ).execute()
        slides = presentation.get('slides', [])
        if slide_index > len(slides):
            return f"Error: Slide index {slide_index} out of bounds (valid range: 1-{len(slides)})."

        slide = slides[slide_index - 1]
        result = {
            "presentationId": presentation.get('presentationId', presentation_id),
            "slideIndex": slide_index,
            "slideObjectId": slide.get('objectId'),
            "elements": [
                summarize_page_element(element)
                for element in slide.get('pageElements', [])
            ],
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting slide elements: {str(e)}"

if __name__ == "__main__":
    mcp.run()

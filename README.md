# Google Slides MCP Server

A Model Context Protocol (MCP) server that enables AI agents (like Claude Desktop, Gemini CLI, etc.) to natively create and manipulate Google Slides presentations. 

It provides tools to create decks, add slides, update slide text placeholders, and delete slides.

## Features / Tools
- `slides_create_presentation`: Creates a new presentation.
- `slides_add_slide`: Adds a slide with a specified layout at a given index.
- `slides_update_slide`: Updates the Title, Body, and Speaker Notes of a slide using a 1-based index.
- `slides_delete_slide`: Deletes a slide by its 1-based index.
- `slides_get_presentation`: Retrieves metadata and slide count for a presentation.

## Prerequisites & Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/artemu78/google-slides-mcp.git
   cd google-slides-mcp
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## How to get `credentials.json`

To authorize the server to modify your presentations, you need a Google Cloud OAuth 2.0 Client ID.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Navigate to **APIs & Services > Library** and enable the **Google Slides API**.
4. Navigate to **APIs & Services > OAuth consent screen** and configure it for "External" or "Internal" use. Add your email as a test user if External.
5. Navigate to **APIs & Services > Credentials**.
6. Click **Create Credentials** -> **OAuth client ID**.
7. Select **Desktop app** as the Application type.
8. Click **Download JSON** and save the file inside the root of this project as `credentials.json`.

## How to Run

### Interactive Testing (MCP Inspector)
You can test the server interactively before attaching it to an AI agent:
```bash
npx @modelcontextprotocol/inspector python3 google_slides_mcp.py
```
*Note: On your very first run, it will open your default web browser asking you to log into your Google account to grant permissions.*

### Adding to an MCP Client (e.g., Claude Desktop or Gemini CLI)
Add the following configuration to your client's `mcp.json` or `mcpServers.json` file. Ensure the path to the script is absolute.

```json
{
  "mcpServers": {
    "google-slides": {
      "command": "python3",
      "args": [
        "/absolute/path/to/google_slides_mcp/google_slides_mcp.py"
      ],
      "env": {}
    }
  }
}
```

## Running Tests

Unit tests are included to verify critical logic (like extracting the correct placeholders from the complex Google Slides API response).

To run the tests:
```bash
python3 -m unittest discover tests
```

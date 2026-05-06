<<<<<<< Updated upstream
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
=======
# Google Slides MCP Setup and Authentication

This project uses OAuth 2.0 user credentials to call the Google Slides API.
You need two files in the project directory:

- `credentials.json` (OAuth client credentials from Google Cloud)
- `token.json` (user access/refresh token generated after login)

## 1) Create Google Cloud OAuth credentials (`credentials.json`)

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable required APIs:
   - Google Slides API
   - Google Drive API
4. Configure OAuth consent screen:
   - Choose **External** or **Internal** (based on your workspace setup).
   - Fill required app info.
   - Add test users if your app is in testing mode.
5. Go to **APIs & Services -> Credentials**.
6. Click **Create Credentials -> OAuth client ID**.
7. Choose application type **Desktop app**.
8. Download JSON and save it as `credentials.json` in this repository root.

## 2) Install Python dependencies

If needed, install dependencies used by this project:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib mcp pydantic
```

If you use a virtual environment, activate it before installing.

## 3) Generate or refresh `token.json`

Run this command from the project root:

```bash
python -c "from google_slides_mcp import get_credentials; get_credentials(); print('token.json created')"
```

What happens:

- If `token.json` is valid, it is reused.
- If token is expired but has refresh token, it is refreshed automatically.
- If refresh is not possible, browser-based OAuth login starts.
- After successful login, a new `token.json` is saved.

## 4) Force clean re-authentication (optional)

If scopes changed or token is broken, delete and regenerate:

```bash
rm -f token.json
python -c "from google_slides_mcp import get_credentials; get_credentials(); print('token.json created')"
```

## 5) Why `python google_slides_mcp.py` may not create token immediately

Running:

```bash
python google_slides_mcp.py
```

starts the MCP server (`mcp.run()`), but does **not** call `get_credentials()` right away.
Credentials are requested only when a tool calls `get_slides_service()` for the first time.

The `python -c ...get_credentials()` command triggers auth immediately, which is why it reliably creates `token.json` on demand.

## 6) Troubleshooting

- **`credentials.json not found`**  
  Place `credentials.json` in the same directory as `google_slides_mcp.py`.

- **Browser did not open**  
  Open the printed auth URL manually and complete consent.

- **`invalid_client` or redirect issues**  
  Ensure credential type is **Desktop app** OAuth client.

- **`access_denied` or app not verified/test mode restrictions**  
  Add your Google account as a test user in OAuth consent screen.

- **Token refresh errors**  
  Delete `token.json` and authenticate again.

## 7) Security notes

- Do not commit `credentials.json` or `token.json`.
- Rotate/recreate OAuth credentials if you suspect leakage.
- Keep OAuth scopes minimal for your use case.

>>>>>>> Stashed changes

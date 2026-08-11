# Google Slides MCP Server

A Model Context Protocol (MCP) server that enables AI agents (like Claude Desktop, Gemini CLI, etc.) to natively create and manipulate Google Slides presentations.

It provides tools to create decks, add slides, update slide text placeholders, and delete slides.

## Features / Tools

- `create_presentation`: Creates a new Google Slides presentation.
- `add_slide`: Adds a slide with a specified layout at an optional 1-based insertion index.
- `duplicate_slide`: Duplicates a slide using its 1-based index.
- `rearrange_slides`: Moves slides using a mapping of current 1-based slide numbers to new 1-based positions; unspecified slides retain their relative order.
- `batch_update`: Runs raw Google Slides `presentations.batchUpdate` requests, including the full Google Slides API request surface.
- `search_icons`: Searches the bundled Tabler icon catalog by name and style.
- `get_icon_url`: Resolves an exact Tabler icon name to its configured public PNG URL.
- `insert_icon`: Inserts a public Tabler PNG into a slide at a position and size measured in points.
- `update_slide`: Updates the title, body, and speaker notes of a slide using its 1-based index.
- `apply_dark_theme`: Applies a configurable dark background, text colors, and font family to every slide.
- `export_thumbnails`: Exports every slide as a PNG thumbnail to a local directory for visual QA.
- `export_slide_thumbnail`: Exports one slide selected by its 1-based index to a specific local PNG path.
- `compose_slide`: Clears selected placeholders and composes a slide from positioned native text and shape elements.
- `delete_slide`: Deletes a slide using its 1-based index.
- `get_presentation`: Retrieves presentation metadata and details for its slides.
- `get_slide_elements`: Retrieves object IDs, element types, text, sizes, and transforms for one slide so individual elements can be edited with `batch_update`.

## Prerequisites & Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/artemu78/google-slides-mcp.git
    cd google-slides-mcp
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Authentication Setup

This project uses OAuth 2.0 user credentials to call the Google Slides API.
You need two files in the project directory:

- `credentials.json` (OAuth client credentials from Google Cloud)
- `token.json` (user access/refresh token generated after login)

### 1) Create Google Cloud OAuth credentials (`credentials.json`)

1.  **Create a Project**: Open [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or select an existing one).
2.  **Enable APIs**: Navigate to **APIs & Services > Library**. Search for and **Enable** the following:
    - **Google Slides API**
    - **Google Drive API**
3.  **Configure OAuth Consent Screen**:
    - Go to **APIs & Services > OAuth consent screen**.
    - Choose **User Type**:
        - **Internal**: If you have a Google Workspace and want to limit access to your organization.
        - **External**: If you are using a personal `@gmail.com` account.
    - Fill in the required **App information** (App name, User support email, Developer contact info).
    - **Add Scope**: Add only `https://www.googleapis.com/auth/drive.file`.
      This non-sensitive, per-file scope lets the server create presentations and
      continue editing files created by this OAuth app. It does not grant access
      to arbitrary existing presentations solely from a pasted URL or ID.
    - **Add Test Users**: **CRITICAL STEP** for External apps in "Testing" status. Add your own Google email address here. Only these users will be able to log in.
4.  **Create Credentials**:
    - Go to **APIs & Services > Credentials**.
    - Click **Create Credentials > OAuth client ID**.
    - Select **Application type**: **Desktop app**.
    - Give it a name (e.g., "Google Slides MCP").
5.  **Download JSON**: After creation, click **Download JSON** for the new credential. Rename the file to `credentials.json` and move it to the root of this repository.

### 2) Generate `token.json` (The "Login" Step)

If you previously authorized this server with different scopes, delete the old
`token.json` first so Google issues a new grant containing only `drive.file`.

Run this command from the project root to trigger the browser-based authentication flow. **Make sure to log into the browser with the same Google account you added as a Test User.**

```bash
python3 -c "from google_slides_mcp import get_credentials; get_credentials(); print('token.json created')"
```

**What happens:**
- Your browser will open a Google login page.
- You might see a "Google hasn't verified this app" warning (common for test apps). Click **Advanced > Go to [App Name] (unsafe)** to proceed.
- Grant the requested permissions.
- Once finished, you will see "The authentication flow is complete" in your browser.
- A `token.json` file will be created in your project folder, which contains your access and refresh tokens.

## Usage with Gemini CLI

### Adding the server
Add the following configuration to your Gemini CLI configuration (usually in `~/.gemini/mcp.json` or as specified in the CLI documentation). Ensure the path to the script is absolute.

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

### Tabler icon PNG catalog

The server uses the bundled `tabler-icons-main/icons` folders as its searchable
catalog. Google Slides cannot insert these local SVG files directly, so upload
PNG versions to a publicly readable HTTP(S) location with this layout:

```text
<base URL>/dark/outline/<icon-name>.png
<base URL>/dark/filled/<icon-name>.png
<base URL>/light/outline/<icon-name>.png
<base URL>/light/filled/<icon-name>.png
```

Then configure the MCP server process with `TABLER_ICONS_BASE_URL`. The value is
the catalog root before the `outline` and `filled` directories:

```json
{
  "mcpServers": {
    "google-slides": {
      "command": "python3",
      "args": ["/absolute/path/to/google_slides_mcp/google_slides_mcp.py"],
      "env": {
        "TABLER_ICONS_BASE_URL": "https://assets.example.com/tabler-icons"
      }
    }
  }
}
```

MCP clients should use this sequence:

1. Call `search_icons` with a human-friendly query such as `arrow right`.
2. Use the returned exact icon name with `insert_icon`, or call
   `get_icon_url` when only the public asset URL is needed.
3. Pass `presentation_id`, a 1-based `slide_index`, and `x`, `y`, `width`, and
   `height` in points to `insert_icon`. Set `theme` to `dark` (black, default)
   or `light` (#E5E7EB) to match the slide background.

The insertion tool validates the name against the bundled catalog before it
calls Google. Google fetches the PNG once and stores a copy in the presentation.
The public PNG must satisfy the Google Slides image limits: PNG, JPEG, or GIF;
less than 50 MB; no more than 25 megapixels; and a URL no longer than 2 KB.

#### Convert and upload the bundled Tabler icons

The resumable batch script renders transparent 96×96 PNGs into a cache outside
the repository, then uses one AWS CLI `s3 sync` operation. It produces a `dark`
black catalog or a `light` #E5E7EB catalog. It reads the bucket, region, and AWS credentials from
`[mcp_servers.s3-uploader.env]` in
`~/.codex/config.toml`; credentials are never printed. Install the prerequisites
first (`brew install librsvg awscli` on macOS), then preview or run the sync:

```bash
python3 scripts/upload_tabler_icons.py --dry-run
python3 scripts/upload_tabler_icons.py --upload
```

To use an existing local AWS CLI profile instead, provide the profile, bucket,
region, and desired theme explicitly:

```bash
python3 scripts/upload_tabler_icons.py --upload --theme light \
  --aws-profile default --bucket mcp-server-storage --region us-east-1
```

The sync sets `Content-Type: image/png`, does not delete remote objects, and does
not set an ACL. Existing PNGs are reconverted only when the source SVG is newer.
The resulting catalog root is normally
`https://<bucket>.s3.<region>.amazonaws.com/tabler-icons`. Google Slides can use
that URL only when the PNG objects are publicly retrievable over HTTPS through
the bucket policy or another configured public endpoint.

### ⚠️ Note on `/mcp auth`
**Do NOT use `/mcp auth google-slides`** in Gemini CLI. This server handles its own authentication via the Python script. If you attempt to use `/mcp auth`, you may see an error like:
`Failed to authenticate with MCP server 'google-slides': Cannot perform dynamic registration without issuer`

Instead, ensure you have followed the **Authentication Setup** steps above before using the server with the CLI.

## How to Run & Test

### Interactive Testing (MCP Inspector)
You can test the server interactively:
```bash
npx @modelcontextprotocol/inspector python3 google_slides_mcp.py
```

### Running Tests
Unit tests are included to verify critical logic:
```bash
python3 -m unittest discover tests
```

## Raw `batch_update` text colors

`updateTextStyle.style.foregroundColor` is an `OptionalColor`, so its RGB value
must be nested under `opaqueColor`:

```json
{
  "updateTextStyle": {
    "objectId": "text-box-id",
    "textRange": {"type": "ALL"},
    "style": {
      "foregroundColor": {
        "opaqueColor": {
          "rgbColor": {"red": 0, "green": 0.44, "blue": 0.75}
        }
      }
    },
    "fields": "foregroundColor"
  }
}
```

For convenience, this tool also accepts `"foregroundColor": "#0070C0"` and
converts it to the wrapper above. A direct
`"foregroundColor": {"rgbColor": ...}` is rejected locally with a validation
message before the Google API is called. This rule applies only to text style:
shape and page fills still use `solidFill.color` as a `Color`, where a direct
`{"rgbColor": ...}` is correct.

## Troubleshooting

- **`credentials.json not found`**: Place `credentials.json` in the same directory as `google_slides_mcp.py`.
- **Browser did not open**: Open the printed auth URL manually and complete consent.
- **`invalid_client`**: Ensure credential type is **Desktop app** OAuth client.
- **Token refresh errors**: Delete `token.json` and authenticate again.

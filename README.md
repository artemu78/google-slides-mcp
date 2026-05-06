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


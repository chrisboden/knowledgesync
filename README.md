# Use Google Docs as a Knowledge Base for LLMs

This utility automatically synchronizes Google Docs and Sheets from a specified Google Drive folder to local files and generates rich metadata to be used as a knowledge base for LLMs:
- Google Docs are converted to Markdown files with rich metadata
- Google Sheets are converted to CSV files with rich metadata
- Uses async processing for efficient metadata generation via LLM
- Produces a manifest containing metadata for each file

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Google Cloud Project and APIs:
   1. Go to [Google Cloud Console](https://console.cloud.google.com/)
   2. Create a new project (or select an existing one)
   3. Enable the required APIs:
      - Go to "APIs & Services" > "Library"
      - Enable "Google Drive API"
      - Enable "Google Sheets API"
      - Click "Enable" for each
   4. Configure OAuth consent screen:
      - Go to "APIs & Services" > "OAuth consent screen"
      - Select "External" user type
      - Fill in the application name and user support email
      - Add your email as a test user
   5. Create OAuth 2.0 credentials:
      - Go to "APIs & Services" > "Credentials"
      - Click "Create Credentials" > "OAuth client ID"
      - Choose "Desktop application" as the application type
      - Name your client
      - Download the credentials JSON file
      - Save it as `credentials.json` in the project root

4. Create a `.env` file with:
   ```
   # Google Drive folder ID (from the folder's URL)
   # Example URL: https://drive.google.com/drive/folders/1234567890abcdef
   # Folder ID would be: 1234567890abcdef
   SOURCE_FOLDER_ID=your_google_drive_folder_id

   # Local destination folder for synced files
   # Use absolute path for best results
   DESTINATION_FOLDER=path/to/local/folder

   # OpenRouter Configuration (for AI metadata extraction)
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   OPENROUTER_API_KEY=your_openrouter_api_key
   ```

## Usage

### One-time sync:
```bash
python main.py
```

### Automated hourly sync (macOS):
1. Make the sync script executable:
   ```bash
   chmod +x sync_docs.sh
   ```

2. Copy the launchd plist to your user's LaunchAgents:
   ```bash
   cp com.gdocs-sync.service.plist ~/Library/LaunchAgents/
   ```

3. Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.gdocs-sync.service.plist
   ```

## Features

- Automatic sync of Google Workspace files:
  - Google Docs to Markdown
  - Google Sheets to CSV (one CSV per worksheet)
- Delta updates (only syncs changed files)
- Rich metadata generation:
  - AI-powered metadata extraction for both documents and spreadsheets
  - Only generates metadata for new or modified files
  - Parallel processing using async API calls
  - Maintains metadata manifests for quick lookups
- Clean image handling (references without base64 data)
- Colored progress output
- Error handling and logging
- Secure OAuth2 authentication
- Automated scheduling via launchd (macOS)

## Directory Structure

```
.
├── .env_example                         # Rename to .env and add your own values
├── .gitignore                           # Git ignore rules
├── README.md                            # Project documentation
├── credentials_example.json             # Rename to credentials.json and add your values
├── main.py                              # Main sync script
├── utils/                               # Utility modules
│   ├── __init__.py                     # Module exports
│   ├── google_drive_ops.py             # Google Drive operations
│   ├── google_sheets_ops.py            # Google Sheets operations
│   ├── document_metadata_ops.py        # Document metadata operations
│   └── spreadsheet_metadata_ops.py     # Spreadsheet metadata operations
├── prompts/                             # AI prompt templates
│   ├── extract_document_metadata.md     # Document metadata extraction prompt
│   └── extract_spreadsheet_metadata.md  # Spreadsheet metadata extraction prompt
├── requirements.txt                     # Python dependencies
├── sync_docs.sh                         # Sync automation script
├── com.gdocs-sync.service.plist         # macOS launch daemon config
└── destination_folder/                  # Your configured sync destination
    ├── documents/                       # Synchronized markdown documents
    │   ├── @manifest.json              # Document metadata manifest
    │   ├── document1.md                # Converted Google Docs
    │   └── document2.md
    └── spreadsheets/                   # Synchronized CSV files
        ├── @manifest.json              # Spreadsheet metadata manifest
        ├── spreadsheet1/               # Each spreadsheet gets its own directory
        │   ├── Sheet1.csv             # One CSV per worksheet
        │   └── Sheet2.csv
        └── spreadsheet2/
            └── Sheet1.csv
```

## Metadata Management

The utility maintains two manifest files:
1. `documents/@manifest.json` - Document metadata including:
   - Document summaries
   - Topics and categories
   - Document sections
   - Last update timestamps
   - Processing status

2. `spreadsheets/@manifest.json` - Spreadsheet metadata including:
   - Spreadsheet purpose and content
   - Data types and relationships
   - Worksheet descriptions
   - Last update timestamps
   - Processing status

Metadata is only generated when:
- A new file is added
- An existing file is modified
- A file's metadata is missing or incomplete

## Monitoring

- Check sync status: `launchctl list | grep gdocs-sync`
- View logs:
  ```bash
  tail -f sync.log     # For sync output
  tail -f sync.error.log  # For error messages
  ```

## Troubleshooting

1. If authentication fails:
   - Delete `token.pickle` and try again
   - Ensure `credentials.json` is in the project root
   - Check you're added as a test user in OAuth consent screen

2. If sync fails:
   - Check the Google Drive folder ID is correct
   - Ensure you have read access to the source folder
   - Review error messages in `sync.error.log`

3. If scheduled sync isn't running:
   - Check service status: `launchctl list | grep gdocs-sync`
   - Ensure paths in `com.gdocs-sync.service.plist` are correct
   - Review system logs: `log show --predicate 'subsystem == "com.gdocs-sync.service"'`

4. If metadata extraction fails:
   - Check OpenRouter API key and base URL in `.env`
   - Verify the file content is accessible
   - Look for token limit warnings in the logs

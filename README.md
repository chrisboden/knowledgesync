# Google Workspace to Local Sync Utility

This utility automatically synchronizes Google Docs and Sheets from a specified Google Drive folder to local files:
- Google Docs are converted to Markdown files
- Google Sheets are converted to CSV files
- Includes AI-powered metadata extraction for documents
- Uses async processing for efficient metadata generation
- Handles image references cleanly

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

The utility will:
- Authenticate with Google Drive through the following process:
  1. First, set up credentials:
     - Download `credentials.json` from Google Cloud Console
     - Place it in the project root directory
     - Note: This file contains sensitive data and is gitignored
     - Use `credentials_example.json` as a template for required format
  
  2. On first run:
     - A browser window will open automatically
     - Select your Google account
     - You may see a warning that the app is not verified - this is expected for development
     - Click "Continue" (or "Advanced" > "Go to [Project Name]" if warned)
     - Review and accept the requested permissions:
       • Read access to Google Drive files
       • View and manage Google Drive files that you have opened/created
     - After accepting, you can close the browser window
     - The utility will save the authentication token locally for future use

Note: If you're not already added as a test user:
1. Go to Google Cloud Console > "OAuth consent screen"
2. Under "Test users" click "Add Users" 
3. Enter your Google account email
4. Click "Save"
5. Wait 5-10 minutes for changes to propagate
6. Try authenticating again

Important: Never commit `credentials.json` to version control. Instead:
- Use the provided `credentials_example.json` as a template
- Copy it to `credentials.json`
- Fill in your actual credentials from Google Cloud Console

## Features

- Automatic sync of Google Workspace files:
  - Google Docs to Markdown
  - Google Sheets to CSV (one CSV per worksheet)
- Delta updates (only syncs changed files)
- Efficient metadata management for documents:
  - Only generates metadata for new or modified files
  - Parallel processing using async API calls
  - Maintains metadata manifest for quick lookups
- Clean image handling (references without base64 data)
- AI-powered metadata extraction using OpenRouter
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
├── drive_ops.py                         # Google Drive operations
├── sheets_ops.py                        # Google Sheets operations
├── metadata_ops.py                      # Metadata extraction operations
├── requirements.txt                     # Python dependencies
├── sync_docs.sh                         # Sync automation script
├── com.gdocs-sync.service.plist         # macOS launch daemon config
└── destination_folder/                  # Your configured sync destination
    ├── documents/                       # Synchronized markdown documents
    │   ├── @manifest.json              # Document metadata manifest
    │   ├── document1.md                # Converted Google Docs
    │   └── document2.md
    └── spreadsheets/                   # Synchronized CSV files
        ├── spreadsheet1/               # Each spreadsheet gets its own directory
        │   ├── Sheet1.csv             # One CSV per worksheet
        │   └── Sheet2.csv
        └── spreadsheet2/
            └── Sheet1.csv
```

## Metadata Management

The utility maintains a `@manifest.json` file in your documents directory that tracks:
- Document metadata (summaries, topics, sections)
- Last update timestamps
- Processing status

Metadata is only generated for documents when:
- A new document is added
- An existing document is modified
- A document's metadata is missing or incomplete

Note: Spreadsheet files are stored as raw CSV without additional metadata.

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
   - Verify the document content is accessible
   - Look for token limit warnings in the logs 

## Project Structure

```
.
├── .env_example                         # Rename to .env and add your own values
├── .gitignore                           # Git ignore rules
├── README.md                            # Project documentation
├── credentials_example.json             # Rename to credentials.json and add the values from Google Cloud Console
├── main.py                              # Main sync script
├── drive_ops.py                         # Google Drive operations
├── sheets_ops.py                        # Google Sheets operations
├── metadata_ops.py                      # Metadata extraction operations
├── requirements.txt                     # Python dependencies
├── sync_docs.sh                         # Sync automation script
├── com.gdocs-sync.service.plist         # macOS launch daemon config
└── destination_folder/                  # Your configured sync destination
    ├── documents/                       # Synchronized markdown documents
    │   ├── @manifest.json              # Document metadata manifest
    │   ├── document1.md                # Converted Google Docs
    │   └── document2.md
    └── spreadsheets/                   # Synchronized CSV files
        ├── spreadsheet1/               # Each spreadsheet gets its own directory
        │   ├── Sheet1.csv             # One CSV per worksheet
        │   └── Sheet2.csv
        └── spreadsheet2/
            └── Sheet1.csv
```

### Manifest File Structure

The `@manifest.json` in your documents directory maintains the sync state and metadata:

```json
[
    {
        "id": "AI-Career-Accelerator-March2025",
        "title": "AI Career Accelerator",
        "last_modified": "2024-03-20T10:30:00Z",
        "last_synced": "2024-03-20T10:35:00Z",
        "metadata": {
            "summary": "The AI Career Accelerator is a 3-week cohort-based course designed to help tech professionals master AI tools, build real projects, and supercharge their career growth. It focuses on understanding durable human skills, applying AI models, and developing a career plan for the AI age, with hands-on experience, skill assessment, and real-world applications.",
            "wordCount": 1450,
            "source": "Markdown Document",
            "language": "en",
            "primaryTopics": [
                "Artificial Intelligence",
                "Career Development",
                "Technology Training",
                "Professional Skills"
            ],
            "questionTypes": [
                "how-to",
                "what",
                "why",
                "career advice"
            ],
            "useCases": [
                "career advancement",
                "skill development",
                "technology adoption",
                "training programs"
            ],
            "audience": "Tech professionals, product managers, engineers, data scientists, tech leaders, founders, career changers",
            "documentSections": [
                {
                    "sectionTitle": "Course Overview",
                    "summary": "Introduces the AI Career Accelerator, highlighting the importance of AI skills, the challenge of keeping up with AI advancements, and the course's focus on durable human skills and AI integration."
                },
                // ... other sections ...
            ],
            "about": "This document is a course overview for the 'AI Career Accelerator,' designed to equip tech professionals with the skills and knowledge necessary to thrive in an AI-driven world. It details the course objectives, target audience, curriculum, and expected outcomes, emphasizing practical AI applications and career planning."
        }
    },
    // ... other documents ...
]
```
Note: The `destination_folder/` directory and its contents are gitignored since they contain your synchronized content. The structure above shows an example of how files are organized after syncing. 

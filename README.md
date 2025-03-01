# Use Google Docs as a Knowledge Base for AI Agents

Extend the capbilities of Cursor Composer and other agentic AI tools by providing them with the knowledge they need to do useful work for you.

This utility automatically synchronizes Google Docs and Sheets from multiple Google Drive folders to local files and generates rich metadata to be used as a knowledge base for LLMs:
- Google Docs are converted to Markdown files with rich metadata
- Google Sheets are converted to CSV files with rich metadata
- Uses async processing for efficient metadata generation via LLM
- Produces a manifest containing metadata for each file
- Supports multiple Google Drive folders with separate local destinations

## Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/chrisboden/knowledgesync.git
   cd knowledgesync
   ```

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
      - Go directly to [OAuth consent screen setup](https://console.cloud.google.com/apis/credentials/consent)
      - Select "External" user type (unless you have Google Workspace)
      - Fill in the required fields:
         - App name: Your app name (e.g., "Knowledge Sync")
         - User support email: Your email
         - Developer contact email: Your email
      - Skip adding scopes (they'll be added automatically)
      - Add your email as a test user
      - You can skip optional fields - they're not needed for testing
   5. Create OAuth 2.0 credentials:
      - Go to "APIs & Services" > "Credentials"
      - Click "Create Credentials" > "OAuth client ID"
      - Choose "Desktop application" as the application type
      - Name your client (e.g., "Knowledge Sync Desktop")
      - Download the credentials JSON file
      - Save it as `credentials.json` in the project root

   > **Note**: If you get stuck in a loop on the branding page, use the direct link to the OAuth consent screen: https://console.cloud.google.com/apis/credentials/consent

4. Create a `.env` file with:
   ```
   # Google Drive folder IDs (from the folder URLs)
   # Example URL: https://drive.google.com/drive/folders/1234567890abcdef
   # Specify as a JSON object mapping folder names to IDs:
   DRIVE_FOLDERS={"knowledge": "folder_id_1", "projects": "folder_id_2", "team": "folder_id_3"}

   # Local destination folder for synced files
   # Use absolute path for best results
   DESTINATION_FOLDER=/path/to/local/folder

   # OpenRouter Configuration (for AI metadata extraction)
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   OPENROUTER_API_KEY=your_openrouter_api_key
   ```

   Each folder in `DRIVE_FOLDERS` will be synced to its own subdirectory under `DESTINATION_FOLDER`. For example:
   - `knowledge` folder syncs to `DESTINATION_FOLDER/knowledge/`
   - `projects` folder syncs to `DESTINATION_FOLDER/projects/`
   - `team` folder syncs to `DESTINATION_FOLDER/team/`

## Usage

### One-time sync (Google Drive to Local):
```bash
python main.py
```

### Two-way sync (Google Drive to Local and Local to Google Drive):
```bash
python main.py --two-way
```

### Push-only sync (Local to Google Drive):
```bash
python push_to_drive.py
```

### Clean up sync state (after manual file deletions):
```bash
python clean_sync_state.py
```
This utility helps maintain a clean sync state by:
- Validating all entries in the sync state against both local files and Google Drive
- Removing entries for files that no longer exist on either side
- Creating a backup of the sync state file before making changes
- Displaying detailed information about what was removed

### Upgrading to Two-Way Sync

If you're upgrading from a previous version with one-way sync only:

1. **Backup your synced folders** first
2. **Clean your sync state**: `python clean_sync_state.py`
3. **Run a pull operation**: `python main.py` (to ensure local files are updated)
4. **Then run a push operation**: `python push_to_drive.py` (to establish file relationships)
5. **Update your services** if using automated syncing:
   ```bash
   cp com.gdocs-sync.service.plist ~/Library/LaunchAgents/
   cp com.gdocs-push.service.plist ~/Library/LaunchAgents/
   launchctl unload ~/Library/LaunchAgents/com.gdocs-sync.service.plist
   launchctl load ~/Library/LaunchAgents/com.gdocs-sync.service.plist
   launchctl unload ~/Library/LaunchAgents/com.gdocs-push.service.plist
   launchctl load ~/Library/LaunchAgents/com.gdocs-push.service.plist
   ```

Remember that local changes will now be pushed to Google Drive, so be mindful of what you edit locally. Run `clean_sync_state.py` after manual file deletions.

### Dedicated push tool:
```bash
python push_to_drive.py
```

### Automated hourly sync (macOS):
1. Make the sync script executable:
   ```bash
   chmod +x sync_docs.sh
   ```

2. Edit the sync service plist to set your workspace path:
   ```bash
   # Replace /path/to/your/workspace with your actual workspace path
   sed -i '' "s|/Users/chrisboden/Desktop/trycursor|$(pwd)|g" com.gdocs-sync.service.plist
   ```

3. Copy the launchd plist to your user's LaunchAgents:
   ```bash
   cp com.gdocs-sync.service.plist ~/Library/LaunchAgents/
   ```

4. Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.gdocs-sync.service.plist
   ```

### Automated hourly push (macOS):
1. Make the push script executable:
   ```bash
   chmod +x push_to_drive.sh
   ```

2. Edit the push service plist to set your workspace path:
   ```bash
   # Replace /path/to/your/workspace with your actual workspace path
   sed -i '' "s|/Users/chrisboden/Dropbox/tools/knowledgesync|$(pwd)|g" com.gdocs-push.service.plist
   ```

3. Copy the launchd plist to your user's LaunchAgents:
   ```bash
   cp com.gdocs-push.service.plist ~/Library/LaunchAgents/
   ```

4. Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.gdocs-push.service.plist
   ```

5. Check that services are running:
   ```bash
   launchctl list | grep -E 'gdocs-sync|gdocs-push'
   # Should show two entries with the services listed
   ```

6. If services are not running or show exit codes, unload and reload:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.gdocs-sync.service.plist
   launchctl load ~/Library/LaunchAgents/com.gdocs-sync.service.plist
   launchctl unload ~/Library/LaunchAgents/com.gdocs-push.service.plist
   launchctl load ~/Library/LaunchAgents/com.gdocs-push.service.plist
   ```

## Features

- Support for multiple Google Drive folders:
  - Each folder syncs to its own subdirectory
  - Independent metadata tracking per folder
  - Parallel processing of folders
- Automatic sync of Google Workspace files:
  - Google Docs to Markdown
  - Google Sheets to CSV (one CSV per worksheet)
- Two-way sync support:
  - Push local changes back to Google Drive
  - Create new files in Google Drive from local files
  - Track file relationships between local and remote
- Spreadsheet ID verification:
  - Verifies spreadsheet IDs match expected titles before updating
  - Provides clear warnings for mismatches
  - Displays all file IDs during sync operations for transparency
- Sync state maintenance utilities:
  - Clean up sync state after manual file deletions
  - Prevent errors from missing files or incorrect IDs
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
├── .env                                # Environment configuration (created from .env_example)
├── .env_example                        # Template for environment variables
├── .gitignore                         # Git ignore rules
├── README.md                          # Project documentation
├── credentials.json                    # Your Google OAuth credentials (created from credentials_example.json)
├── main.py                           # Main sync script
├── token.pickle                       # Google API auth token (auto-generated on first run)
├── temp/                             # Temporary files for knowledge base queries
│   └── knowledge_base.md             # Generated knowledge base (temporary)
├── tools/                            # CLI tools
│   ├── README.md                     # Tools documentation
│   └── use_knowledge.py              # Knowledge base query tool
├── utils/                            # Utility modules
│   ├── __init__.py                  # Module exports
│   ├── google_drive_ops.py          # Google Drive operations
│   ├── google_sheets_ops.py         # Google Sheets operations
│   ├── document_metadata_ops.py     # Document metadata operations
│   └── spreadsheet_metadata_ops.py  # Spreadsheet metadata operations
├── prompts/                          # AI prompt templates
│   ├── extract_document_metadata.md  # Document metadata extraction prompt
│   └── extract_spreadsheet_metadata.md  # Spreadsheet metadata extraction prompt
├── requirements.txt                  # Python dependencies
├── sync_docs.sh                      # Sync automation script
├── com.gdocs-sync.service.plist      # macOS launch daemon config
└── destination_folder/               # Your configured sync destination (name matches DESTINATION_FOLDER)
    ├── knowledge/                    # First Drive folder sync
    │   ├── documents/               # Synchronized markdown documents
    │   │   ├── @manifest.json      # Document metadata manifest (auto-generated)
    │   │   └── *.md               # Converted Google Docs
    │   └── spreadsheets/          # Synchronized CSV files
    │       ├── @manifest.json     # Spreadsheet metadata manifest (auto-generated)
    │       └── */                 # One directory per spreadsheet
    │           └── *.csv         # One CSV per worksheet
    ├── projects/                   # Second Drive folder sync (same structure)
    │   ├── documents/
    │   └── spreadsheets/
    └── team/                      # Third Drive folder sync (same structure)
        ├── documents/
        └── spreadsheets/
```

## Metadata Management

The utility maintains two manifest files per folder:
1. `{folder}/documents/@manifest.json` - Document metadata including:
   - Document summaries
   - Topics and categories
   - Document sections
   - Last update timestamps
   - Processing status

2. `{folder}/spreadsheets/@manifest.json` - Spreadsheet metadata including:
   - Spreadsheet purpose and content
   - Data types and relationships
   - Worksheet descriptions
   - Last update timestamps
   - Processing status

Metadata is only generated when:
- A new file is added
- An existing file is modified
- A file's metadata is missing or incomplete

## Using Your Knowledge Base with AI Agents

The synchronized documents and their metadata can be used by AI agents to perform knowledge work. The repository includes a tool called `use_knowledge.py` that demonstrates this capability:

### How the Knowledge Tool Works

1. **Intelligent Document Selection**:
   - Takes a natural language query about your knowledge base
   - Uses LLM to analyze document and spreadsheet manifests
   - Selects the most relevant files based on metadata (summaries, topics, sections)
   - Supports searching across all synchronized folders

2. **Knowledge Base Creation**:
   - Combines selected documents and spreadsheets into a single markdown file
   - Converts spreadsheets to markdown tables for easy reading
   - Includes metadata about why each document was selected
   - Creates a temporary file that can be used by AI agents

3. **Agent Integration**:
   - Perfect for use with AI agents (like Cursor's Composer)
   - Agents can read the combined knowledge base
   - Makes informed responses based on your organization's knowledge
   - Maintains source attribution for all information

### Example Usage

Command line:
```bash
python tools/use_knowledge.py "what are our current AI initiatives?"
```

The tool will:
1. Search through all document and spreadsheet manifests
2. Select relevant files based on the query
3. Create a combined markdown file with:
   - Document content
   - Converted spreadsheet data
   - Selection rationales
   - Source attribution

This temporary knowledge base can then be used by AI agents to:
- Answer questions about your organization
- Analyze project data
- Generate reports
- Make recommendations based on your actual documents

### Benefits

- **Context-Aware**: Agents work with your actual organizational knowledge
- **Source Attribution**: All information can be traced back to source documents
- **Cross-Document Analysis**: Combines information from multiple sources
- **Format Agnostic**: Works with both documents and spreadsheets
- **Efficient**: Uses metadata for quick document selection
- **Privacy-Focused**: Works with your local files, no cloud storage needed

## Monitoring

- Check sync status: `launchctl list | grep gdocs-sync`
- Check push status: `launchctl list | grep gdocs-push`
- View logs:
  ```bash
  tail -f sync.log     # For sync output
  tail -f sync.error.log  # For sync error messages
  tail -f push.log     # For push output
  tail -f push.error.log  # For push error messages
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

3. If spreadsheet sync has issues:
   - Run `python clean_sync_state.py` to ensure the sync state is clean
   - Check if spreadsheet IDs or names have changed
   - Look for warning messages about spreadsheet ID verification

4. If files were manually deleted:
   - Run `python clean_sync_state.py` to update the sync state
   - This prevents errors when trying to update non-existent files

5. If scheduled sync isn't running:
   - Check service status: `launchctl list | grep gdocs-sync`
   - Ensure paths in `com.gdocs-sync.service.plist` are correct
   - Review system logs: `log show --predicate 'subsystem == "com.gdocs-sync.service"'`

6. If metadata extraction fails:
   - Check OpenRouter API key and base URL in `.env`
   - Verify the file content is accessible
   - Look for token limit warnings in the logs

## Spreadsheet Formatting

When working with spreadsheets, follow these guidelines to ensure proper synchronization:

1. **Use Standard CSV Formatting**:
   - Avoid using comment lines (lines starting with `#`) in CSV files
   - Ensure CSV files have proper headers as the first row
   - Maintain consistent column structure throughout the file

2. **Spreadsheet Structure**:
   - Each spreadsheet is a directory containing one or more CSV files
   - Each CSV file represents a worksheet in Google Sheets
   - The directory name becomes the spreadsheet name in Google Drive

Example of properly formatted CSV:
```
Name,Email,Role,Department
John Doe,john@example.com,Developer,Engineering
Jane Smith,jane@example.com,Designer,Product
```

Improper formatting (avoid):
```
# This is a comment line that may cause sync issues
Name,Email,Role,Department
John Doe,john@example.com,Developer,Engineering
```

## Testing

Several test scripts are available in the `tests` directory, to verify functionality:

1. `test_new_files.py` - Tests creation of new files & verifies that new files are properly created in Google Drive.
2. `test_edit_files.py` - This test verifies that edits to local files are properly synced to Google Drive.
3. `test_sync.py` - Tests basic two-way sync functionality
4. `test_spreadsheet_sync.py` - Tests spreadsheet sync functionality
5. `test_push_service.py` - Tests the configuration of the automated push service
6. `test_edit_files_standard.py` - Tests editing and syncing existing files with standard CSV formatting

Run each test with:
```
python3 tests/test_script_name.py
```

For more detailed testing instructions, see [TESTING.md](TESTING.md).

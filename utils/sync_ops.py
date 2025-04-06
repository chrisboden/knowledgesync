"""
Two-way sync operations for the knowledgesync utility.
Handles syncing local changes back to Google Drive.
"""
import os
import json
from pathlib import Path
from datetime import datetime
import pytz
from termcolor import colored
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import re

class SyncOperations:
    def __init__(self, base_dir: str, folder_name: str = None):
        """Initialize sync operations.
        
        Args:
            base_dir (str): Base directory for all synced content
            folder_name (str): Name of the specific folder configuration being synced
        """
        self.base_dir = Path(base_dir)
        self.folder_name = folder_name
        self.docs_dir = self.base_dir / (folder_name if folder_name else "") / "documents"
        self.sheets_dir = self.base_dir / (folder_name if folder_name else "") / "spreadsheets"
        self.sync_state_file = self.base_dir / (folder_name if folder_name else "") / ".sync_state.json"
        self.drive_service = None
        self.sheets_service = None
        
    def set_services(self, drive_service, sheets_service):
        """Set the Google Drive and Sheets services."""
        self.drive_service = drive_service
        self.sheets_service = sheets_service
        
    def _load_sync_state(self):
        """Load the sync state from file."""
        if self.sync_state_file.exists():
            try:
                return json.loads(self.sync_state_file.read_text())
            except json.JSONDecodeError:
                print(colored("✗ Invalid sync state file. Creating new one.", "red"))
                return self._create_default_sync_state()
        else:
            return self._create_default_sync_state()
            
    def _create_default_sync_state(self):
        """Create a default sync state."""
        return {
            "last_sync": datetime.now(pytz.UTC).isoformat(),
            "file_map": {
                "documents": {},  # Maps local file paths to Google Drive file IDs
                "spreadsheets": {}  # Maps local directory paths to Google Drive file IDs
            }
        }
        
    def _save_sync_state(self, sync_state):
        """Save the sync state to file."""
        self.sync_state_file.write_text(json.dumps(sync_state, indent=2))
        
    def detect_local_changes(self):
        """
        Detect local file changes since the last sync.
        Returns a dictionary of changed files.
        """
        sync_state = self._load_sync_state()
        last_sync = datetime.fromisoformat(sync_state["last_sync"])
        
        changes = {
            "documents": {
                "modified": [],
                "new": []
            },
            "spreadsheets": {
                "modified": [],
                "new": []
            }
        }
        
        # Check documents
        for md_file in self.docs_dir.glob("*.md"):
            if md_file.name == "@manifest.json":
                continue
                
            file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=pytz.UTC)
            rel_path = str(md_file.relative_to(self.docs_dir))
            
            if rel_path in sync_state["file_map"]["documents"]:
                # Existing file
                if file_mtime > last_sync:
                    changes["documents"]["modified"].append(md_file)
            else:
                # New file
                changes["documents"]["new"].append(md_file)
                
        # Check spreadsheets (directories containing CSV files)
        processed_dirs = set()  # Track directories we've already processed
        
        for sheet_dir in self.sheets_dir.iterdir():
            if not sheet_dir.is_dir() or sheet_dir.name.startswith("@"):
                continue
                
            # Check if any CSV in the directory has been modified
            csv_files = list(sheet_dir.glob("*.csv"))
            if not csv_files:
                continue
                
            # Get the modification time of the newest file
            try:
                newest_mtime = max(
                    datetime.fromtimestamp(f.stat().st_mtime, tz=pytz.UTC)
                    for f in csv_files
                )
            except Exception as e:
                print(colored(f"✗ Error checking file times for {sheet_dir.name}: {str(e)}", "red"))
                continue
                
            rel_path = str(sheet_dir.relative_to(self.sheets_dir))
            
            # Skip if we've already processed this directory
            if rel_path in processed_dirs:
                print(colored(f"Skipping already processed directory: {rel_path}", "yellow"))
                continue
                
            processed_dirs.add(rel_path)
            
            if rel_path in sync_state["file_map"]["spreadsheets"]:
                # Existing spreadsheet
                if newest_mtime > last_sync:
                    changes["spreadsheets"]["modified"].append(sheet_dir)
                    print(colored(f"Detected modified spreadsheet: {rel_path}", "cyan"))
            else:
                # New spreadsheet
                changes["spreadsheets"]["new"].append(sheet_dir)
                print(colored(f"Detected new spreadsheet: {rel_path}", "cyan"))
                
        return changes
        
    def update_document_in_drive(self, md_file: Path, folder_id: str):
        """
        Update an existing Google Doc with content from a local markdown file.
        Returns the Google Drive file ID if successful, None otherwise.
        """
        if not self.drive_service:
            print(colored("✗ Drive service not initialized", "red"))
            return None
            
        try:
            sync_state = self._load_sync_state()
            rel_path = str(md_file.relative_to(self.docs_dir))
            file_id = sync_state["file_map"]["documents"].get(rel_path)
            
            if not file_id:
                print(colored(f"✗ No Drive file ID found for {rel_path}", "red"))
                return None
                
            # Read markdown content
            md_content = md_file.read_text(encoding='utf-8')
            
            # Create a temporary file with the markdown content
            temp_file = Path(f"{md_file}.temp")
            temp_file.write_text(md_content, encoding='utf-8')
            
            try:
                # Update the existing file instead of creating a new one
                media = MediaFileUpload(str(temp_file), mimetype='text/markdown')
                
                # Update the file's content
                updated_file = self.drive_service.files().update(
                    fileId=file_id,
                    media_body=media,
                    fields='id'
                ).execute()
                
                print(colored(f"↻ Updated {md_file.name} in Google Drive", "green"))
                return updated_file['id']
                
            finally:
                # Clean up temp file
                if temp_file.exists():
                    temp_file.unlink()
                    
        except HttpError as e:
            print(colored(f"✗ Error updating document in Drive: {str(e)}", "red"))
            return None
        except Exception as e:
            print(colored(f"✗ Unexpected error updating document: {str(e)}", "red"))
            return None
            
    def create_document_in_drive(self, md_file: Path, folder_id: str):
        """
        Create a new Google Doc from a local markdown file.
        Returns the Google Drive file ID if successful, None otherwise.
        """
        if not self.drive_service:
            print(colored("✗ Drive service not initialized", "red"))
            return None
            
        try:
            # Read markdown content
            md_content = md_file.read_text(encoding='utf-8')
            
            # Create a temporary file with the markdown content
            temp_file = Path(f"{md_file}.temp")
            temp_file.write_text(md_content, encoding='utf-8')
            
            try:
                # Upload as a new file
                media = MediaFileUpload(str(temp_file), mimetype='text/markdown')
                file_metadata = {
                    'name': md_file.stem,
                    'mimeType': 'application/vnd.google-apps.document',
                    'parents': [folder_id]
                }
                
                # Create the file
                file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                
                # Update the sync state
                sync_state = self._load_sync_state()
                rel_path = str(md_file.relative_to(self.docs_dir))
                sync_state["file_map"]["documents"][rel_path] = file['id']
                self._save_sync_state(sync_state)
                
                print(colored(f"+ Created {md_file.name} in Google Drive", "green"))
                return file['id']
                
            finally:
                # Clean up temp file
                if temp_file.exists():
                    temp_file.unlink()
                    
        except HttpError as e:
            print(colored(f"✗ Error creating document in Drive: {str(e)}", "red"))
            return None
        except Exception as e:
            print(colored(f"✗ Unexpected error creating document: {str(e)}", "red"))
            return None
            
    def verify_spreadsheet_id(self, spreadsheet_id, expected_name):
        """
        Verify that a spreadsheet ID corresponds to a spreadsheet with the expected name.
        
        Args:
            spreadsheet_id (str): The Google Drive spreadsheet ID to verify
            expected_name (str): The expected name of the spreadsheet
            
        Returns:
            bool: True if verification succeeds, False otherwise
        """
        if not self.sheets_service:
            print(colored("✗ Sheets service not initialized", "red"))
            return False
            
        try:
            # Get the spreadsheet metadata
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            # Get the title from the properties
            title = spreadsheet.get('properties', {}).get('title', '')
            
            # Check if the title matches or contains what we expect
            if expected_name in title:
                print(colored(f"✓ Verified spreadsheet ID {spreadsheet_id} with title '{title}'", "green"))
                return True
            else:
                print(colored(f"WARNING: Spreadsheet ID {spreadsheet_id} has title '{title}', expected '{expected_name}'", "yellow"))
                return False
        except HttpError as e:
            print(colored(f"WARNING: Could not verify spreadsheet ID {spreadsheet_id}: {str(e)}", "red"))
            return False
        except Exception as e:
            print(colored(f"WARNING: Unexpected error verifying spreadsheet ID: {str(e)}", "red"))
            return False
            
    def update_spreadsheet_in_drive(self, sheet_dir: Path, folder_id: str):
        """
        Update an existing Google Sheet with content from local CSV files.
        Returns the Google Drive file ID if successful, None otherwise.
        """
        if not self.drive_service or not self.sheets_service:
            print(colored("✗ Drive or Sheets service not initialized", "red"))
            return None
            
        try:
            sync_state = self._load_sync_state()
            rel_path = str(sheet_dir.relative_to(self.sheets_dir))
            file_id = sync_state["file_map"]["spreadsheets"].get(rel_path)
            
            if not file_id:
                print(colored(f"✗ No Drive file ID found for {rel_path}", "red"))
                return None
                
            # Print information about the spreadsheet being updated
            print(colored(f"Updating spreadsheet: {rel_path}", "cyan"))
            print(colored(f"Spreadsheet ID: {file_id}", "cyan"))
                
            # Verify the spreadsheet ID matches the expected name
            verification_passed = self.verify_spreadsheet_id(file_id, rel_path)
            if not verification_passed:
                print(colored(f"WARNING: Proceeding with potentially incorrect spreadsheet ID: {file_id}", "yellow"))
                
            # Get all CSV files in the directory
            csv_files = list(sheet_dir.glob("*.csv"))
            if not csv_files:
                print(colored(f"✗ No CSV files found in {sheet_dir.name}", "red"))
                return None
                
            # Get the current sheets in the spreadsheet
            try:
                spreadsheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=file_id
                ).execute()
                
                existing_sheets = {sheet['properties']['title']: sheet['properties']['sheetId'] 
                                for sheet in spreadsheet.get('sheets', [])}
            except HttpError as e:
                print(colored(f"✗ Error getting spreadsheet info: {str(e)}", "red"))
                # If we can't get the spreadsheet, it might have been deleted
                # Create a new one instead
                return self.create_spreadsheet_in_drive(sheet_dir, folder_id)
            
            # Process each CSV file
            for csv_file in csv_files:
                worksheet_name = csv_file.stem
                
                # Read CSV data
                with open(csv_file, 'r', encoding='utf-8') as f:
                    import csv
                    reader = csv.reader(f)
                    values = list(reader)
                
                # Check if the worksheet exists
                if worksheet_name in existing_sheets:
                    # Update existing worksheet
                    try:
                        # Clear existing content
                        self.sheets_service.spreadsheets().values().clear(
                            spreadsheetId=file_id,
                            range=worksheet_name
                        ).execute()
                        
                        # Update with new content
                        self.sheets_service.spreadsheets().values().update(
                            spreadsheetId=file_id,
                            range=worksheet_name,
                            valueInputOption='RAW',
                            body={'values': values}
                        ).execute()
                    except HttpError as e:
                        print(colored(f"✗ Error updating worksheet {worksheet_name}: {str(e)}", "red"))
                else:
                    # Add new worksheet
                    try:
                        self.sheets_service.spreadsheets().batchUpdate(
                            spreadsheetId=file_id,
                            body={
                                'requests': [
                                    {
                                        'addSheet': {
                                            'properties': {
                                                'title': worksheet_name
                                            }
                                        }
                                    }
                                ]
                            }
                        ).execute()
                        
                        # Add content to new worksheet
                        self.sheets_service.spreadsheets().values().update(
                            spreadsheetId=file_id,
                            range=worksheet_name,
                            valueInputOption='RAW',
                            body={'values': values}
                        ).execute()
                    except HttpError as e:
                        print(colored(f"✗ Error adding new worksheet {worksheet_name}: {str(e)}", "red"))
            
            print(colored(f"↻ Updated {sheet_dir.name} in Google Drive", "green"))
            return file_id
            
        except HttpError as e:
            print(colored(f"✗ Error updating spreadsheet in Drive: {str(e)}", "red"))
            return None
        except Exception as e:
            print(colored(f"✗ Unexpected error updating spreadsheet: {str(e)}", "red"))
            return None
            
    def create_spreadsheet_in_drive(self, sheet_dir: Path, folder_id: str):
        """
        Create a new Google Sheet from local CSV files.
        Returns the Google Drive file ID if successful, None otherwise.
        """
        if not self.drive_service or not self.sheets_service:
            print(colored("✗ Drive or Sheets service not initialized", "red"))
            return None
            
        try:
            # Get all CSV files in the directory
            csv_files = list(sheet_dir.glob("*.csv"))
            if not csv_files:
                print(colored(f"✗ No CSV files found in {sheet_dir.name}", "red"))
                return None
                
            # Create a new spreadsheet
            spreadsheet = self.sheets_service.spreadsheets().create(
                body={
                    'properties': {
                        'title': sheet_dir.name
                    }
                }
            ).execute()
            
            file_id = spreadsheet['spreadsheetId']
            
            # Move the spreadsheet to the correct folder
            file = self.drive_service.files().get(
                fileId=file_id,
                fields='parents'
            ).execute()
            
            previous_parents = ",".join(file.get('parents', []))
            
            # Move the file to the new folder
            self.drive_service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            
            # Get the existing sheets to find the default sheet
            sheet_metadata = self.sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
            sheets = sheet_metadata.get('sheets', [])
            
            # If there's a default sheet, we'll use it for the first CSV
            default_sheet_id = None
            default_sheet_title = None
            if sheets:
                default_sheet_id = sheets[0]['properties']['sheetId']
                default_sheet_title = sheets[0]['properties']['title']
            
            # Process each CSV file
            for i, csv_file in enumerate(csv_files):
                worksheet_name = csv_file.stem
                
                # Read CSV data
                with open(csv_file, 'r', encoding='utf-8') as f:
                    import csv
                    reader = csv.reader(f)
                    values = list(reader)
                
                if i == 0 and default_sheet_id is not None:
                    # Rename the default sheet
                    try:
                        self.sheets_service.spreadsheets().batchUpdate(
                            spreadsheetId=file_id,
                            body={
                                'requests': [
                                    {
                                        'updateSheetProperties': {
                                            'properties': {
                                                'sheetId': default_sheet_id,
                                                'title': worksheet_name
                                            },
                                            'fields': 'title'
                                        }
                                    }
                                ]
                            }
                        ).execute()
                        
                        # Add content to the first sheet
                        self.sheets_service.spreadsheets().values().update(
                            spreadsheetId=file_id,
                            range=worksheet_name,
                            valueInputOption='RAW',
                            body={'values': values}
                        ).execute()
                    except HttpError as e:
                        print(colored(f"✗ Error updating default sheet: {str(e)}", "red"))
                        # Try using the default sheet title instead
                        try:
                            self.sheets_service.spreadsheets().values().update(
                                spreadsheetId=file_id,
                                range=default_sheet_title,
                                valueInputOption='RAW',
                                body={'values': values}
                            ).execute()
                            
                            # Now try to rename it
                            self.sheets_service.spreadsheets().batchUpdate(
                                spreadsheetId=file_id,
                                body={
                                    'requests': [
                                        {
                                            'updateSheetProperties': {
                                                'properties': {
                                                    'sheetId': default_sheet_id,
                                                    'title': worksheet_name
                                                },
                                                'fields': 'title'
                                            }
                                        }
                                    ]
                                }
                            ).execute()
                        except HttpError as e2:
                            print(colored(f"✗ Error updating sheet content: {str(e2)}", "red"))
                else:
                    # Add new worksheet
                    try:
                        add_sheet_response = self.sheets_service.spreadsheets().batchUpdate(
                            spreadsheetId=file_id,
                            body={
                                'requests': [
                                    {
                                        'addSheet': {
                                            'properties': {
                                                'title': worksheet_name
                                            }
                                        }
                                    }
                                ]
                            }
                        ).execute()
                        
                        # Add content to new worksheet
                        self.sheets_service.spreadsheets().values().update(
                            spreadsheetId=file_id,
                            range=worksheet_name,
                            valueInputOption='RAW',
                            body={'values': values}
                        ).execute()
                    except HttpError as e:
                        print(colored(f"✗ Error adding new sheet: {str(e)}", "red"))
            
            # Update the sync state
            sync_state = self._load_sync_state()
            rel_path = str(sheet_dir.relative_to(self.sheets_dir))
            sync_state["file_map"]["spreadsheets"][rel_path] = file_id
            self._save_sync_state(sync_state)
            
            print(colored(f"+ Created {sheet_dir.name} in Google Drive", "green"))
            return file_id
            
        except HttpError as e:
            print(colored(f"✗ Error creating spreadsheet in Drive: {str(e)}", "red"))
            return None
        except Exception as e:
            print(colored(f"✗ Unexpected error creating spreadsheet: {str(e)}", "red"))
            return None
            
    def _retry_drive_operation(self, operation, max_retries=3, initial_delay=1):
        """
        Retry a Drive API operation with exponential backoff.
        
        Args:
            operation: Function that performs the Drive API call
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds between retries
            
        Returns:
            The result of the operation if successful, None otherwise
        """
        import time
        
        for attempt in range(max_retries):
            try:
                return operation()
            except HttpError as e:
                if e.resp.status == 500:  # Internal Server Error
                    delay = initial_delay * (2 ** attempt)  # Exponential backoff
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        print(colored(f"Drive API error (attempt {attempt + 1}/{max_retries}), retrying in {delay}s...", "yellow"))
                        time.sleep(delay)
                        continue
                print(colored(f"Drive API error: {str(e)}", "red"))
                return None
            except Exception as e:
                print(colored(f"Unexpected error: {str(e)}", "red"))
                return None
        return None

    def _verify_file_access(self, file_id):
        """
        Verify that we can access a file in Drive.
        
        Args:
            file_id: The Google Drive file ID to verify
            
        Returns:
            bool: True if file is accessible, False otherwise
        """
        try:
            self.drive_service.files().get(
                fileId=file_id,
                fields='id, name'
            ).execute()
            return True
        except HttpError as e:
            if e.resp.status in [403, 404]:  # Permission denied or Not found
                print(colored(f"File {file_id} is not accessible (HTTP {e.resp.status})", "red"))
            else:
                print(colored(f"Error checking file access: {str(e)}", "red"))
            return False
        except Exception as e:
            print(colored(f"Unexpected error checking file access: {str(e)}", "red"))
            return False

    def _clean_markdown_for_drive(self, content):
        """
        Clean markdown content before sending to Drive.
        Removes image references that would cause issues.
        """
        # Remove image reference definitions at the end of the file
        content = re.sub(r'\n\[image\d+\]: <image_reference_image\d+>\s*$', '', content, flags=re.MULTILINE)
        
        # Remove inline image references
        content = re.sub(r'!\[\]\[image\d+\]\s*', '', content)
        
        return content

    def push_local_changes(self, folder_id: str):
        """
        Push local changes to Google Drive.
        Returns a dictionary with statistics about the sync operation.
        """
        if not self.drive_service or not self.sheets_service:
            print(colored("✗ Drive or Sheets service not initialized", "red"))
            return {
                "documents": {"updated": 0, "created": 0, "failed": 0},
                "spreadsheets": {"updated": 0, "created": 0, "failed": 0}
            }
            
        print(colored("\nChecking for local changes...", "cyan"))
        
        # Get list of docs in the Drive folder
        def list_files():
            return self.drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
        results = self._retry_drive_operation(list_files)
        if not results:
            print(colored("Failed to list files in Drive folder", "red"))
            return {
                "documents": {"updated": 0, "created": 0, "failed": 0},
                "spreadsheets": {"updated": 0, "created": 0, "failed": 0}
            }
            
        drive_files = {f['name']: f['id'] for f in results.get('files', [])}
        print(colored(f"Found {len(drive_files)} files in Drive folder", "cyan"))
            
        # Load sync state
        sync_state = self._load_sync_state()
        last_sync = datetime.fromisoformat(sync_state["last_sync"])
        
        stats = {
            "documents": {"updated": 0, "created": 0, "failed": 0},
            "spreadsheets": {"updated": 0, "created": 0, "failed": 0}
        }
        
        # Process each local markdown file
        for md_file in self.docs_dir.glob("*.md"):
            if md_file.name == "@manifest.json":
                continue
                
            print(colored(f"\nProcessing {md_file.name}", "cyan"))
            
            # Check if file has been modified since last sync
            file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=pytz.UTC)
            if file_mtime <= last_sync:
                print(colored(f"Skipping {md_file.name} - no changes since last sync", "yellow"))
                continue
                
            # Check if file exists in Drive
            drive_name = md_file.stem
            drive_id = drive_files.get(drive_name)
            
            if drive_id:
                print(colored(f"Found in Drive with ID: {drive_id}", "green"))
                
                # Verify we can access the file
                if not self._verify_file_access(drive_id):
                    print(colored(f"Cannot access file {drive_id}, will try to create new", "yellow"))
                    if self.create_document_in_drive(md_file, folder_id):
                        stats["documents"]["created"] += 1
                    else:
                        stats["documents"]["failed"] += 1
                    continue
                
                # Update existing file
                try:
                    # Read markdown content and clean it
                    md_content = md_file.read_text(encoding='utf-8')
                    cleaned_content = self._clean_markdown_for_drive(md_content)
                    
                    # Create a temporary file with the cleaned content
                    temp_file = Path(f"{md_file}.temp")
                    temp_file.write_text(cleaned_content, encoding='utf-8')
                    
                    try:
                        # Update the file's content with retry
                        def update_file():
                            media = MediaFileUpload(str(temp_file), mimetype='text/markdown')
                            return self.drive_service.files().update(
                                fileId=drive_id,
                                media_body=media,
                                fields='id'
                            ).execute()
                            
                        if self._retry_drive_operation(update_file):
                            # Update sync state with the file ID
                            rel_path = str(md_file.relative_to(self.docs_dir))
                            sync_state["file_map"]["documents"][rel_path] = drive_id
                            
                            print(colored(f"↻ Updated {md_file.name} in Google Drive", "green"))
                            stats["documents"]["updated"] += 1
                        else:
                            print(colored(f"Failed to update {md_file.name} after retries", "red"))
                            stats["documents"]["failed"] += 1
                    finally:
                        # Clean up temp file
                        if temp_file.exists():
                            temp_file.unlink()
                except Exception as e:
                    print(colored(f"✗ Error updating {md_file.name}: {str(e)}", "red"))
                    stats["documents"]["failed"] += 1
            else:
                print(colored(f"Not found in Drive - will create new", "yellow"))
                # Create new file
                if self.create_document_in_drive(md_file, folder_id):
                    stats["documents"]["created"] += 1
                else:
                    stats["documents"]["failed"] += 1
                    
        # Process spreadsheet changes (directories containing CSV files)
        processed_dirs = set()
        
        for sheet_dir in self.sheets_dir.iterdir():
            if not sheet_dir.is_dir() or sheet_dir.name.startswith("@"):
                continue
                
            rel_path = str(sheet_dir.relative_to(self.sheets_dir))
            if rel_path in processed_dirs:
                continue
                
            processed_dirs.add(rel_path)
            
            # Check if any CSV in the directory has been modified since last sync
            csv_files = list(sheet_dir.glob("*.csv"))
            if csv_files:
                newest_mtime = max(
                    datetime.fromtimestamp(f.stat().st_mtime, tz=pytz.UTC)
                    for f in csv_files
                )
                if newest_mtime <= last_sync:
                    print(colored(f"Skipping {sheet_dir.name} - no changes since last sync", "yellow"))
                    continue
            
            # Check if spreadsheet exists in sync state
            file_id = sync_state["file_map"]["spreadsheets"].get(rel_path)
            
            if file_id:
                # Update existing spreadsheet
                if self.update_spreadsheet_in_drive(sheet_dir, folder_id):
                    stats["spreadsheets"]["updated"] += 1
                else:
                    stats["spreadsheets"]["failed"] += 1
            else:
                # Create new spreadsheet
                if self.create_spreadsheet_in_drive(sheet_dir, folder_id):
                    stats["spreadsheets"]["created"] += 1
                else:
                    stats["spreadsheets"]["failed"] += 1
                    
        # Save the updated sync state
        sync_state["last_sync"] = datetime.now(pytz.UTC).isoformat()
        self._save_sync_state(sync_state)
        
        return stats 
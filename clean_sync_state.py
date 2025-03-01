#!/usr/bin/env python3
"""
Script to clean up the sync state file by removing entries for files that no longer exist.
This resolves issues when files are manually deleted locally or in Google Drive
but the sync state file wasn't updated.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from termcolor import colored
from utils.google_drive_ops import DriveOperations
from utils.google_sheets_ops import SheetsOperations

def setup():
    """Initialize the application and check requirements."""
    print(colored("Starting sync state cleanup...", "cyan"))
    
    # Load environment variables
    load_dotenv()
    drive_folders = os.getenv('DRIVE_FOLDERS')
    dest_folder = os.getenv('DESTINATION_FOLDER')
    
    if not drive_folders or not dest_folder:
        print(colored("✗ Missing environment variables. Please check .env file.", "red"))
        print("Required variables:")
        print("- DRIVE_FOLDERS: JSON object mapping folder names to Google Drive folder IDs")
        print("- DESTINATION_FOLDER: Path to local destination folder")
        sys.exit(1)
    
    try:
        drive_folders = json.loads(drive_folders)
    except json.JSONDecodeError:
        print(colored("✗ DRIVE_FOLDERS must be a valid JSON object", "red"))
        sys.exit(1)
    
    # Create destination folder if it doesn't exist
    dest_path = Path(dest_folder)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    return drive_folders, dest_path

def clean_sync_state(folder_name, folder_id, base_dir):
    """Clean the sync state for a specific folder."""
    print(colored(f"\nCleaning sync state for folder: {folder_name}", "cyan"))
    
    # Paths
    folder_path = base_dir / folder_name
    sync_state_file = folder_path / ".sync_state.json"
    docs_dir = folder_path / "documents"
    sheets_dir = folder_path / "spreadsheets"
    
    # Check if sync state file exists
    if not sync_state_file.exists():
        print(colored(f"✗ No sync state file found for {folder_name}", "red"))
        return False
    
    # Load the sync state
    try:
        with open(sync_state_file, 'r') as f:
            sync_state = json.load(f)
    except Exception as e:
        print(colored(f"✗ Error loading sync state: {str(e)}", "red"))
        return False
    
    # Create backup of sync state
    backup_file = sync_state_file.with_suffix(f".json.bak.{os.path.getmtime(sync_state_file)}")
    try:
        with open(backup_file, 'w') as f:
            json.dump(sync_state, f, indent=2)
        print(colored(f"✓ Created backup of sync state: {backup_file.name}", "green"))
    except Exception as e:
        print(colored(f"✗ Error creating backup: {str(e)}", "red"))
        return False
    
    # Initialize Drive operations
    google_drive_ops = DriveOperations(base_dir, folder_name)
    if not google_drive_ops.authenticate():
        print(colored(f"✗ Failed to authenticate with Google Drive for {folder_name}", "red"))
        return False
    
    # Initialize Sheets operations
    google_sheets_ops = SheetsOperations(base_dir, folder_name)
    if not google_sheets_ops.authenticate(google_drive_ops.get_credentials()):
        print(colored(f"✗ Failed to authenticate with Google Sheets for {folder_name}", "red"))
        return False
    
    # Check documents
    invalid_docs = []
    valid_docs = {}
    
    print("\nChecking document mappings...")
    for doc_path, file_id in sync_state["file_map"]["documents"].items():
        # Check if file exists locally
        local_file = docs_dir / doc_path
        local_exists = local_file.exists()
        
        # Check if file exists in Google Drive
        try:
            drive_file = google_drive_ops.service.files().get(fileId=file_id, fields="name").execute()
            drive_exists = True
        except Exception:
            drive_exists = False
        
        if not local_exists and not drive_exists:
            print(colored(f"- Removing {doc_path} (missing on both sides)", "yellow"))
            invalid_docs.append(doc_path)
        elif not local_exists:
            print(colored(f"- Removing {doc_path} (missing locally)", "yellow"))
            invalid_docs.append(doc_path)
        elif not drive_exists:
            print(colored(f"- Removing {doc_path} (missing in Google Drive)", "yellow"))
            invalid_docs.append(doc_path)
        else:
            valid_docs[doc_path] = file_id
    
    # Update documents in sync state
    sync_state["file_map"]["documents"] = valid_docs
    
    # Check spreadsheets
    invalid_sheets = []
    valid_sheets = {}
    
    print("\nChecking spreadsheet mappings...")
    for sheet_path, file_id in sync_state["file_map"]["spreadsheets"].items():
        # Check if directory exists locally
        local_dir = sheets_dir / sheet_path
        local_exists = local_dir.exists() and local_dir.is_dir()
        
        # Check if file exists in Google Drive
        try:
            drive_file = google_sheets_ops.service.spreadsheets().get(spreadsheetId=file_id).execute()
            drive_exists = True
        except Exception:
            drive_exists = False
        
        if not local_exists and not drive_exists:
            print(colored(f"- Removing {sheet_path} (missing on both sides)", "yellow"))
            invalid_sheets.append(sheet_path)
        elif not local_exists:
            print(colored(f"- Removing {sheet_path} (missing locally)", "yellow"))
            invalid_sheets.append(sheet_path)
        elif not drive_exists:
            print(colored(f"- Removing {sheet_path} (missing in Google Drive)", "yellow"))
            invalid_sheets.append(sheet_path)
        else:
            valid_sheets[sheet_path] = file_id
    
    # Update spreadsheets in sync state
    sync_state["file_map"]["spreadsheets"] = valid_sheets
    
    # Save updated sync state
    try:
        with open(sync_state_file, 'w') as f:
            json.dump(sync_state, f, indent=2)
        print(colored(f"\n✓ Saved updated sync state", "green"))
        
        removed_docs = len(invalid_docs)
        removed_sheets = len(invalid_sheets)
        print(colored(f"✓ Removed {removed_docs} document mapping(s) and {removed_sheets} spreadsheet mapping(s)", "green"))
        
        return True
    except Exception as e:
        print(colored(f"✗ Error saving sync state: {str(e)}", "red"))
        return False

def main():
    """Main entry point."""
    try:
        # Setup and initialize
        drive_folders, dest_path = setup()
        
        # Process each configured folder
        success = True
        for folder_name, folder_id in drive_folders.items():
            result = clean_sync_state(folder_name, folder_id, dest_path)
            if not result:
                success = False
        
        if success:
            print(colored("\nSync state cleanup completed successfully!", "green"))
            print(colored("Now you can run sync operations again with a clean state.", "green"))
        else:
            print(colored("\nSync state cleanup completed with some errors.", "yellow"))
            print(colored("Please check the logs above for details.", "yellow"))
        
    except Exception as e:
        print(colored(f"✗ Cleanup failed: {str(e)}", "red"))
        import traceback
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 
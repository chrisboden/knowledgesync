#!/usr/bin/env python3
"""
Command-line tool for pushing local changes to Google Drive.
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from termcolor import colored
from utils.google_drive_ops import DriveOperations
from utils.google_sheets_ops import SheetsOperations
from utils.sync_ops import SyncOperations

def setup():
    """Initialize the application and check requirements."""
    print(colored("Starting Google Workspace push...", "cyan"))
    
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
    
    # Check for credentials file
    if not os.path.exists('credentials.json'):
        print(colored("✗ credentials.json not found", "red"))
        print("Please download OAuth credentials from Google Cloud Console")
        sys.exit(1)
    
    # Create destination folder if it doesn't exist
    dest_path = Path(dest_folder)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    return drive_folders, dest_path

def print_push_summary(stats):
    """Print a summary of the push operation."""
    print("\nPush Summary:")
    
    print("\nDocuments:")
    print(colored(f"Created: {stats['documents']['created']}", "green"))
    print(colored(f"Updated: {stats['documents']['updated']}", "green"))
    print(colored(f"Failed: {stats['documents']['failed']}", "red"))
    
    print("\nSpreadsheets:")
    print(colored(f"Created: {stats['spreadsheets']['created']}", "green"))
    print(colored(f"Updated: {stats['spreadsheets']['updated']}", "green"))
    print(colored(f"Failed: {stats['spreadsheets']['failed']}", "red"))

def display_sync_state(sync_ops):
    """Display the current sync state for verification before pushing."""
    if not sync_ops:
        print(colored("✗ Cannot display sync state: sync_ops not initialized", "red"))
        return False
        
    try:
        # Directly load the sync state since it might not be loaded yet
        sync_state = sync_ops._load_sync_state()
        if not sync_state:
            print(colored("✗ Cannot display sync state: failed to load sync state", "red"))
            return False
            
        print(colored("\nCurrent sync state:", "cyan"))
        print(f"Last sync: {sync_state.get('last_sync', 'Unknown')}")
        
        if "file_map" in sync_state:
            file_map = sync_state["file_map"]
            
            if "spreadsheets" in file_map and file_map["spreadsheets"]:
                print(colored("\nSpreadsheets:", "cyan"))
                for name, file_id in file_map["spreadsheets"].items():
                    print(f"  - {name}: {file_id}")
            
            if "documents" in file_map and file_map["documents"]:
                print(colored("\nDocuments:", "cyan"))
                for name, file_id in file_map["documents"].items():
                    print(f"  - {name}: {file_id}")
                    
        print() # Add an empty line for readability
        return True
    except Exception as e:
        print(colored(f"✗ Error displaying sync state: {str(e)}", "red"))
        return False

async def push_folder_changes(folder_name, folder_id, base_dir):
    """Push changes for a specific folder to Google Drive."""
    print(colored(f"\nProcessing folder: {folder_name}", "cyan"))
    
    # Initialize Drive operations for this folder
    google_drive_ops = DriveOperations(base_dir, folder_name)
    if not google_drive_ops.authenticate():
        print(colored(f"Skipping folder {folder_name} due to authentication failure", "yellow"))
        return {
            "documents": {"updated": 0, "created": 0, "failed": 0},
            "spreadsheets": {"updated": 0, "created": 0, "failed": 0}
        }
    
    # Initialize Sheets operations with same credentials
    google_sheets_ops = SheetsOperations(base_dir, folder_name)
    if not google_sheets_ops.authenticate(google_drive_ops.get_credentials()):
        print(colored(f"Skipping folder {folder_name} due to Sheets authentication failure", "yellow"))
        return {
            "documents": {"updated": 0, "created": 0, "failed": 0},
            "spreadsheets": {"updated": 0, "created": 0, "failed": 0}
        }
    
    # Initialize Sync operations
    sync_ops = SyncOperations(base_dir, folder_name)
    sync_ops.set_services(google_drive_ops.service, google_sheets_ops.service)
    
    # Display the sync state for verification
    display_sync_state(sync_ops)
    
    # Push local changes to Google Drive
    print(colored("\nPushing local changes to Google Drive...", "cyan"))
    stats = sync_ops.push_local_changes(folder_id)
    
    return stats

async def main():
    """Main entry point."""
    try:
        # Setup and initialize
        drive_folders, dest_path = setup()
        
        # Process each configured folder
        total_stats = {
            "documents": {"updated": 0, "created": 0, "failed": 0},
            "spreadsheets": {"updated": 0, "created": 0, "failed": 0}
        }
        
        for folder_name, folder_id in drive_folders.items():
            # Push changes for this folder
            stats = await push_folder_changes(folder_name, folder_id, dest_path)
            
            # Print folder summary
            print(f"\nSummary for folder {folder_name}:")
            print_push_summary(stats)
            
            # Update total stats
            for doc_type in ["documents", "spreadsheets"]:
                for stat_type in ["updated", "created", "failed"]:
                    total_stats[doc_type][stat_type] += stats[doc_type][stat_type]
        
        # Print overall summary
        print(colored("\nOverall Push Summary:", "cyan"))
        print_push_summary(total_stats)
        
        print(colored("\nPush completed successfully!", "green"))
        
    except Exception as e:
        print(colored(f"✗ Push failed: {str(e)}", "red"))
        import traceback
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 
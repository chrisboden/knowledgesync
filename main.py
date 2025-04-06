"""
Main application for Google Docs/Sheets to Markdown/CSV sync utility.
"""
import os
import sys
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from termcolor import colored
from utils.google_drive_ops import DriveOperations
from utils.google_sheets_ops import SheetsOperations
from utils.document_metadata_ops import DocumentMetadataOperations
from utils.spreadsheet_metadata_ops import SpreadsheetMetadataOperations
from utils.sync_ops import SyncOperations
import pytz
import json

def setup():
    """Initialize the application and check requirements."""
    print(colored("Starting Google Workspace sync...", "cyan"))
    
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

def get_local_file_info(directory: Path, pattern: str = "*.md"):
    """Get information about existing local files."""
    local_files = {}
    for file_path in directory.glob(pattern):
        mtime = datetime.fromtimestamp(
            file_path.stat().st_mtime,
            tz=pytz.UTC
        )
        local_files[file_path.stem] = mtime
    return local_files

async def sync_docs(google_drive_ops, source_folder_id: str, dest_path: Path):
    """Sync Google Docs to local markdown files."""
    print("\nSyncing Google Docs...")
    
    try:
        # Get list of docs in the source folder
        docs = google_drive_ops.list_docs_in_folder(source_folder_id)
        if not docs:
            print(colored("No documents found to sync", "yellow"))
            return
        
        # Get info about existing local files
        docs_dir = google_drive_ops.docs_dir
        local_files = get_local_file_info(docs_dir)
        
        # Track sync statistics
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0, 'removed': 0}
        updated_files = []
        
        # Create set of current Google Doc names for checking deletions
        gdrive_doc_names = {doc['name'] for doc in docs}
        
        # Check for files that need to be removed
        for local_file_name in local_files.keys():
            if local_file_name not in gdrive_doc_names:
                local_file_path = docs_dir / f"{local_file_name}.md"
                try:
                    local_file_path.unlink()
                    print(colored(f"- Removed {local_file_name}.md (deleted from Google Drive)", "yellow"))
                    stats['removed'] += 1
                except Exception as e:
                    print(colored(f"✗ Failed to remove {local_file_name}.md: {str(e)}", "red"))
                    stats['failed'] += 1
        
        # Process each document
        for doc in docs:
            try:
                # Clean up the filename
                base_name = doc['name']
                if base_name.lower().endswith('.md'):
                    base_name = base_name[:-3]
                local_filename = f"{base_name}.md"
                
                # Create Path object for local file
                local_path = docs_dir / local_filename
                
                # Check if we need to update this file
                needs_update = True
                if base_name in local_files:
                    local_mtime = local_files[base_name]
                    doc_mtime = datetime.fromisoformat(doc['modifiedTime'].replace('Z', '+00:00'))
                    if local_mtime >= doc_mtime:
                        print(colored(f"↷ Skipping {local_filename} (up to date)", "cyan"))
                        stats['skipped'] += 1
                        needs_update = False
                
                if needs_update:
                    # Export the document to Markdown
                    content = google_drive_ops.export_doc_to_markdown(doc['id'])
                    if content:
                        # Write to local file
                        local_path.write_text(content, encoding='utf-8')
                        updated_files.append(local_path)
                        if base_name in local_files:
                            print(colored(f"↻ Updated {local_filename}", "green"))
                            stats['updated'] += 1
                        else:
                            print(colored(f"+ Created {local_filename}", "green"))
                            stats['created'] += 1
                    else:
                        print(colored(f"✗ Failed to export {local_filename}", "red"))
                        stats['failed'] += 1
                        
            except Exception as e:
                print(colored(f"✗ Error processing {doc['name']}: {str(e)}", "red"))
                stats['failed'] += 1
        
        return stats, updated_files
        
    except Exception as e:
        print(colored(f"✗ Docs sync failed: {str(e)}", "red"))
        return {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 1, 'removed': 0}, []

async def sync_sheets(google_sheets_ops, source_folder_id: str, dest_path: Path):
    """Sync Google Sheets to local CSV files."""
    print("\nSyncing Google Sheets...")
    
    try:
        # Get list of sheets in the source folder
        sheets = google_sheets_ops.list_sheets_in_folder(source_folder_id)
        if not sheets:
            print(colored("No spreadsheets found to sync", "yellow"))
            return {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0, 'removed': 0}, []
        
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0, 'removed': 0}
        updated_files = []
        
        # Process each spreadsheet
        for sheet in sheets:
            try:
                # Get metadata about the spreadsheet
                metadata = google_sheets_ops.get_sheet_metadata(sheet['id'])
                if not metadata:
                    print(colored(f"✗ Failed to get metadata for {sheet['name']}", "red"))
                    stats['failed'] += 1
                    continue
                
                # Create directory for this spreadsheet
                sheet_dir = google_sheets_ops.sheets_dir / metadata['title']
                sheet_dir.mkdir(exist_ok=True)
                
                # Process each worksheet
                for worksheet in metadata['sheets']:
                    worksheet_name = worksheet['name']
                    csv_path = sheet_dir / f"{worksheet_name}.csv"
                    
                    # Check if we need to update this worksheet
                    needs_update = True
                    if csv_path.exists():
                        local_mtime = datetime.fromtimestamp(
                            csv_path.stat().st_mtime,
                            tz=pytz.UTC
                        )
                        sheet_mtime = datetime.fromisoformat(sheet['modifiedTime'].replace('Z', '+00:00'))
                        if local_mtime >= sheet_mtime:
                            print(colored(f"↷ Skipping {metadata['title']}/{worksheet_name}.csv (up to date)", "cyan"))
                            stats['skipped'] += 1
                            needs_update = False
                    
                    if needs_update:
                        # Export the worksheet to CSV
                        sheet_data = google_sheets_ops.export_sheet_to_csv(sheet['id'], worksheet_name)
                        if sheet_data:
                            # Save the CSV file
                            csv_file = google_sheets_ops.save_sheet_as_csv(
                                sheet['id'],
                                metadata,
                                sheet_data,
                                worksheet_name
                            )
                            if csv_file:
                                updated_files.append(Path(csv_file))
                                if csv_path.exists():
                                    print(colored(f"↻ Updated {metadata['title']}/{worksheet_name}.csv", "green"))
                                    stats['updated'] += 1
                                else:
                                    print(colored(f"+ Created {metadata['title']}/{worksheet_name}.csv", "green"))
                                    stats['created'] += 1
                            else:
                                print(colored(f"✗ Failed to save {worksheet_name}.csv", "red"))
                                stats['failed'] += 1
                        else:
                            print(colored(f"✗ Failed to export {worksheet_name}", "red"))
                            stats['failed'] += 1
                            
            except Exception as e:
                print(colored(f"✗ Error processing {sheet['name']}: {str(e)}", "red"))
                stats['failed'] += 1
        
        return stats, updated_files
        
    except Exception as e:
        print(colored(f"✗ Sheets sync failed: {str(e)}", "red"))
        return {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 1, 'removed': 0}, []

def print_sync_summary(doc_stats, sheet_stats):
    """Print a summary of the sync operation."""
    print("\nSync Summary:")
    print("\nDocuments:")
    print(colored(f"Created: {doc_stats['created']}", "green"))
    print(colored(f"Updated: {doc_stats['updated']}", "green"))
    print(colored(f"Removed: {doc_stats['removed']}", "yellow"))
    print(colored(f"Skipped: {doc_stats['skipped']}", "cyan"))
    print(colored(f"Failed: {doc_stats['failed']}", "red"))
    
    print("\nSpreadsheets:")
    print(colored(f"Created: {sheet_stats['created']}", "green"))
    print(colored(f"Updated: {sheet_stats['updated']}", "green"))
    print(colored(f"Removed: {sheet_stats['removed']}", "yellow"))
    print(colored(f"Skipped: {sheet_stats['skipped']}", "cyan"))
    print(colored(f"Failed: {sheet_stats['failed']}", "red"))

async def push_local_changes(google_drive_ops, google_sheets_ops, folder_id: str, dest_path: Path):
    """Push local changes to Google Drive."""
    print("\nPushing local changes to Google Drive...")
    
    try:
        # Initialize Sync operations
        sync_ops = SyncOperations(dest_path, google_drive_ops.folder_name)
        sync_ops.set_services(google_drive_ops.service, google_sheets_ops.service)
        
        # Push local changes to Google Drive
        stats = sync_ops.push_local_changes(folder_id)
        
        return stats
        
    except Exception as e:
        print(colored(f"✗ Push failed: {str(e)}", "red"))
        return {
            "documents": {"updated": 0, "created": 0, "failed": 1},
            "spreadsheets": {"updated": 0, "created": 0, "failed": 1}
        }

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

async def main():
    """Main entry point."""
    try:
        # Parse command-line arguments
        parser = argparse.ArgumentParser(description='Google Workspace sync utility')
        parser.add_argument('--two-way', action='store_true', help='Enable two-way sync (push local changes to Google Drive)')
        parser.add_argument('--push-only', action='store_true', help='Only push local changes to Google Drive (no pull)')
        args = parser.parse_args()
        
        # Setup and initialize
        drive_folders, dest_path = setup()
        
        # Process each configured folder
        for folder_name, folder_id in drive_folders.items():
            print(colored(f"\nProcessing folder: {folder_name}", "cyan"))
            
            # Initialize Drive operations for this folder
            google_drive_ops = DriveOperations(dest_path, folder_name)
            if not google_drive_ops.authenticate():
                print(colored(f"Skipping folder {folder_name} due to authentication failure", "yellow"))
                continue
            
            # Initialize Sheets operations with same credentials
            google_sheets_ops = SheetsOperations(dest_path, folder_name)
            if not google_sheets_ops.authenticate(google_drive_ops.get_credentials()):
                print(colored(f"Skipping folder {folder_name} due to Sheets authentication failure", "yellow"))
                continue
            
            # Perform operations based on command-line arguments
            if args.push_only:
                # Push-only mode
                push_stats = await push_local_changes(google_drive_ops, google_sheets_ops, folder_id, dest_path)
                print(f"\nPush summary for folder {folder_name}:")
                print_push_summary(push_stats)
            else:
                # Pull from Google Drive
                doc_stats, doc_updated_files = await sync_docs(google_drive_ops, folder_id, dest_path)
                sheet_stats, sheet_updated_files = await sync_sheets(google_sheets_ops, folder_id, dest_path)
                
                # Print folder summary
                print(f"\nPull summary for folder {folder_name}:")
                print_sync_summary(doc_stats, sheet_stats)
                
                # Update metadata if needed
                folder_base = dest_path / folder_name
                
                if doc_updated_files or doc_stats['removed']:
                    print("\nUpdating document metadata...")
                    metadata_ops = DocumentMetadataOperations(folder_base / "documents")
                    await metadata_ops.update_manifest()
                else:
                    print(colored("\nDocument metadata is up to date", "green"))
                
                # Check if we need to update metadata for spreadsheets
                spreadsheet_metadata_ops = SpreadsheetMetadataOperations(folder_base)
                manifest_path = folder_base / "spreadsheets" / "@manifest.json"
                needs_metadata_update = (
                    sheet_updated_files or 
                    sheet_stats['removed'] or 
                    not manifest_path.exists() or
                    (manifest_path.exists() and manifest_path.stat().st_size == 0) or
                    (manifest_path.exists() and len(json.loads(manifest_path.read_text())) == 0)
                )
                
                if needs_metadata_update:
                    print("\nUpdating spreadsheet metadata...")
                    await spreadsheet_metadata_ops.update_manifest()
                else:
                    print(colored("\nSpreadsheet metadata is up to date", "green"))
                
                # Two-way sync: push local changes to Google Drive
                if args.two_way:
                    push_stats = await push_local_changes(google_drive_ops, google_sheets_ops, folder_id, dest_path)
                    print(f"\nPush summary for folder {folder_name}:")
                    print_push_summary(push_stats)
        
        print(colored("\nSync completed successfully!", "green"))
        
    except Exception as e:
        print(colored(f"✗ Sync failed: {str(e)}", "red"))
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 
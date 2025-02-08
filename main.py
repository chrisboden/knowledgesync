"""
Main application for Google Docs to Markdown sync utility.
"""
import os
import sys
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from termcolor import colored
from drive_ops import DriveOperations
from metadata_ops import MetadataOperations
import pytz
import json

def setup():
    """Initialize the application and check requirements."""
    print(colored("Starting Google Docs to Markdown sync...", "cyan"))
    
    # Load environment variables
    load_dotenv()
    source_folder_id = os.getenv('SOURCE_FOLDER_ID')
    dest_folder = os.getenv('DESTINATION_FOLDER')
    
    if not source_folder_id or not dest_folder:
        print(colored("✗ Missing environment variables. Please check .env file.", "red"))
        print("Required variables:")
        print("- SOURCE_FOLDER_ID: The ID of your Google Drive folder")
        print("- DESTINATION_FOLDER: Path to local destination folder")
        sys.exit(1)
    
    # Check for credentials file
    if not os.path.exists('credentials.json'):
        print(colored("✗ credentials.json not found", "red"))
        print("Please download OAuth credentials from Google Cloud Console")
        sys.exit(1)
    
    # Create destination folder if it doesn't exist
    dest_path = Path(dest_folder)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    return source_folder_id, dest_path

def get_local_file_info(dest_path):
    """Get information about existing local files."""
    local_files = {}
    for md_file in dest_path.glob('*.md'):
        # Convert local timestamp to UTC for comparison
        timestamp = datetime.fromtimestamp(md_file.stat().st_mtime)
        utc_time = timestamp.astimezone(pytz.UTC)
        local_files[md_file.stem] = utc_time
    return local_files

def check_manifest_status(dest_path):
    """Check if manifest exists and contains entries for all files."""
    manifest_path = dest_path / "@manifest.json"  # Look for manifest in gdocs directory
    try:
        if not manifest_path.exists():
            print(colored("! No manifest found - will create new one", "yellow"))
            return True  # Need to create manifest
            
        manifest_data = json.loads(manifest_path.read_text())
        manifest_files = {item["fileName"] for item in manifest_data}
        
        # Get all current markdown files
        current_files = {f.name for f in dest_path.glob("*.md")}
        
        # Check for missing files
        missing_files = current_files - manifest_files
        if missing_files:
            print(colored(f"! Found {len(missing_files)} files not in manifest:", "yellow"))
            for file in missing_files:
                print(colored(f"  - {file}", "yellow"))
            return True
            
        # Check for removed files
        removed_files = manifest_files - current_files
        if removed_files:
            print(colored(f"! Found {len(removed_files)} files in manifest that no longer exist:", "yellow"))
            for file in removed_files:
                print(colored(f"  - {file}", "yellow"))
            return True
        
        return False
        
    except json.JSONDecodeError:
        print(colored("! Invalid manifest JSON - will recreate", "yellow"))
        return True  # Invalid manifest, need to recreate
    except Exception as e:
        print(colored(f"! Error checking manifest: {str(e)}", "yellow"))
        return True  # Any other error, recreate manifest

async def sync_docs(drive_ops, source_folder_id: str, dest_path: str):
    """Sync Google Docs to local markdown files."""
    print("Starting Google Docs to Markdown sync...")
    
    try:
        # Convert dest_path to Path object if it isn't already
        dest_path = Path(dest_path)
        
        # Get list of docs in the source folder
        docs = drive_ops.list_docs_in_folder(source_folder_id)
        if not docs:
            print(colored("No documents found to sync", "yellow"))
            return
        
        # Get info about existing local files
        local_files = get_local_file_info(dest_path)
        
        # Track sync statistics
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0, 'removed': 0}
        updated_files = []  # Track which files were created or updated
        
        # Create set of current Google Doc names for checking deletions
        gdrive_doc_names = {doc['name'] for doc in docs}
        
        # Check for files that need to be removed
        for local_file_name in local_files.keys():
            if local_file_name not in gdrive_doc_names:
                local_file_path = dest_path / f"{local_file_name}.md"
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
                # Clean up the filename to prevent double .md extension
                base_name = doc['name']
                # Remove .md extension if it exists in the Google Doc name
                if base_name.lower().endswith('.md'):
                    base_name = base_name[:-3]
                # Add .md extension for local file
                local_filename = f"{base_name}.md"
                
                # Create Path object for local file
                local_path = dest_path / local_filename
                
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
                    content = drive_ops.export_doc_to_markdown(doc['id'])
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
        
        # Print sync summary
        print("\nSync Summary:")
        print(colored(f"Created: {stats['created']}", "green"))
        print(colored(f"Updated: {stats['updated']}", "green"))
        print(colored(f"Removed: {stats['removed']}", "yellow"))
        print(colored(f"Skipped: {stats['skipped']}", "cyan"))
        print(colored(f"Failed: {stats['failed']}", "red"))
        
        # Check if we need to update metadata
        needs_metadata_update = bool(updated_files) or bool(stats['removed']) or check_manifest_status(dest_path)
        
        if needs_metadata_update:
            print("\nUpdating document metadata...")
            metadata_ops = MetadataOperations(dest_path)
            await metadata_ops.update_manifest()
        else:
            print(colored("\nMetadata is up to date", "green"))
        
    except Exception as e:
        print(colored(f"✗ Sync failed: {str(e)}", "red"))
        sys.exit(1)

async def main():
    """Main entry point."""
    try:
        # Setup and initialize
        source_folder_id, dest_path = setup()
        
        # Initialize Drive operations
        drive_ops = DriveOperations()
        if not drive_ops.authenticate():
            sys.exit(1)
        
        # Perform sync
        await sync_docs(drive_ops, source_folder_id, dest_path)
        
    except KeyboardInterrupt:
        print(colored("\n\nSync interrupted by user", "yellow"))
        sys.exit(0)
    except Exception as e:
        print(colored(f"\n✗ Unexpected error: {str(e)}", "red"))
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main()) 
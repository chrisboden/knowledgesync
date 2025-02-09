"""
Metadata operations for spreadsheet analysis and manifest management.
"""
import json
import os
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from termcolor import colored
from dotenv import load_dotenv
from openai import AsyncOpenAI
import pytz
import csv

class SpreadsheetMetadataOperations:
    def __init__(self, base_dir: str):
        """Initialize metadata operations."""
        self.base_dir = Path(base_dir)
        self.spreadsheets_dir = self.base_dir / "spreadsheets"
        self.manifest_path = self.spreadsheets_dir / "@manifest.json"
        self.prompt_template_path = Path("prompts/extract_spreadsheet_metadata.md")
        
        # Load environment variables
        load_dotenv()
        
        # Configure OpenAI client for OpenRouter
        api_key = os.getenv('OPENROUTER_API_KEY')
        base_url = os.getenv('OPENROUTER_BASE_URL')
        
        if not api_key or not base_url:
            print(colored("✗ Missing OpenRouter configuration. Check OPENROUTER_API_KEY and OPENROUTER_BASE_URL in .env", "red"))
            return
            
        print(colored("✓ OpenRouter configuration loaded", "green"))
        
        # Initialize OpenAI client with OpenRouter configuration
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/chrisboden/knowledgesync",
                "X-Title": "GDocs Sync"
            }
        )
        
        # Initialize manifest if it doesn't exist
        if not self.manifest_path.exists():
            self.manifest_path.write_text("[]")
            
        # Load current manifest
        self.manifest = self._load_manifest()
        
    def _load_manifest(self):
        """Load the current manifest file."""
        try:
            if self.manifest_path.exists():
                data = json.loads(self.manifest_path.read_text())
                # Check if manifest has rich metadata
                for entry in data:
                    if not all(key in entry for key in ["about", "summary", "primaryTopics", "dataTypes"]):
                        print(colored("! Manifest lacks rich metadata - will regenerate", "yellow"))
                        return []
                return data
            return []
        except json.JSONDecodeError:
            print(colored("! Invalid manifest JSON - will create new one", "yellow"))
            return []
        except Exception as e:
            print(colored(f"! Error loading manifest: {str(e)}", "yellow"))
            return []
            
    def _save_manifest(self):
        """Save the current manifest to file."""
        try:
            self.manifest_path.write_text(json.dumps(self.manifest, indent=2))
        except Exception as e:
            print(colored(f"✗ Error saving manifest: {str(e)}", "red"))
            
    def _get_prompt_template(self):
        """Get the prompt template for metadata extraction."""
        try:
            return self.prompt_template_path.read_text()
        except Exception as e:
            print(colored(f"✗ Error reading prompt template: {str(e)}", "red"))
            return None
            
    def _read_worksheet_data(self, csv_path: Path):
        """Read data from a CSV worksheet."""
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                return list(reader)
        except Exception as e:
            print(colored(f"✗ Error reading CSV {csv_path.name}: {str(e)}", "red"))
            return None
            
    async def extract_metadata(self, spreadsheet_dir: Path):
        """Extract metadata from a spreadsheet directory."""
        try:
            print(colored(f"\nExtracting metadata for {spreadsheet_dir.name}...", "cyan"))
            
            # Get all CSV files in the spreadsheet directory
            csv_files = list(spreadsheet_dir.glob("*.csv"))
            if not csv_files:
                print(colored("✗ No CSV files found", "red"))
                return None
                
            # Read all worksheet data
            worksheet_contents = {}
            for csv_file in csv_files:
                data = self._read_worksheet_data(csv_file)
                if data:
                    worksheet_contents[csv_file.stem] = data
                    
            if not worksheet_contents:
                print(colored("✗ Failed to read any worksheet data", "red"))
                return None
                
            # Get and check prompt template
            prompt_template = self._get_prompt_template()
            if not prompt_template:
                return None
                
            # Prepare prompt with worksheet data
            prompt = prompt_template.format(
                spreadsheet_title=spreadsheet_dir.name,
                directory_path=str(spreadsheet_dir.relative_to(self.base_dir)),
                worksheet_contents=json.dumps(worksheet_contents, indent=2)
            )
            
            print(colored("Calling OpenRouter API...", "cyan"))
            
            # Call OpenRouter API via OpenAI client
            completion = await self.client.chat.completions.create(
                model="google/gemini-2.0-flash-001",
                messages=[
                    {"role": "system", "content": "You are a Spreadsheet Metadata Extraction Assistant."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            print(colored("Parsing API response...", "cyan"))
            
            # Get response content
            content = completion.choices[0].message.content
            
            # Parse JSON response
            try:
                metadata = json.loads(content)
                # Add system fields
                metadata.update({
                    "lastSynced": datetime.now(timezone.utc).isoformat(),
                    "source": "Google Sheets"
                })
                
                # Update worksheet paths to be relative to base directory
                if "worksheets" in metadata:
                    for worksheet in metadata["worksheets"]:
                        if "csvPath" in worksheet:
                            worksheet["csvPath"] = str(
                                Path("spreadsheets") / spreadsheet_dir.name / worksheet["csvPath"]
                            )
                
                print(colored("✓ Metadata extracted successfully", "green"))
                return metadata
                
            except json.JSONDecodeError as e:
                print(colored(f"✗ Error parsing response: {str(e)}", "red"))
                return None
                
        except Exception as e:
            print(colored(f"✗ Error in metadata extraction: {str(e)}", "red"))
            return None
            
    async def update_manifest(self):
        """Update the manifest with metadata for all spreadsheets."""
        print(colored("\nUpdating spreadsheet metadata...", "cyan"))
        
        # Get all spreadsheet directories
        spreadsheet_dirs = [d for d in self.spreadsheets_dir.iterdir() if d.is_dir()]
        print(colored(f"Found {len(spreadsheet_dirs)} spreadsheets", "cyan"))
        
        stats = {"added": 0, "updated": 0, "failed": 0, "skipped": 0}
        
        for spreadsheet_dir in spreadsheet_dirs:
            try:
                # Check if we need to update this spreadsheet's metadata
                needs_update = True
                existing_entry = next(
                    (item for item in self.manifest if item["title"] == spreadsheet_dir.name),
                    None
                )
                
                if existing_entry and all(key in existing_entry for key in ["about", "summary", "primaryTopics", "dataTypes"]):
                    # Check if any CSV files are newer than last sync
                    last_synced = datetime.fromisoformat(existing_entry["lastSynced"])
                    csv_files = list(spreadsheet_dir.glob("*.csv"))
                    
                    if csv_files:
                        newest_mtime = max(
                            datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                            for f in csv_files
                        )
                        if newest_mtime <= last_synced:
                            print(colored(f"↷ Skipping {spreadsheet_dir.name} (up to date)", "cyan"))
                            stats["skipped"] += 1
                            needs_update = False
                            
                if needs_update:
                    # Extract metadata
                    metadata = await self.extract_metadata(spreadsheet_dir)
                    
                    if metadata:
                        if existing_entry:
                            # Update existing entry
                            self.manifest.remove(existing_entry)
                            self.manifest.append(metadata)
                            print(colored(f"↻ Updated metadata for {spreadsheet_dir.name}", "green"))
                            stats["updated"] += 1
                        else:
                            # Add new entry
                            self.manifest.append(metadata)
                            print(colored(f"+ Added metadata for {spreadsheet_dir.name}", "green"))
                            stats["added"] += 1
                            
                        # Save after each successful update
                        self._save_manifest()
                    else:
                        print(colored(f"✗ Failed to extract metadata for {spreadsheet_dir.name}", "red"))
                        stats["failed"] += 1
                        
            except Exception as e:
                print(colored(f"✗ Error processing {spreadsheet_dir.name}: {str(e)}", "red"))
                stats["failed"] += 1
                
        # Print summary
        print("\nSpreadsheet Metadata Update Summary:")
        print(colored(f"Added: {stats['added']}", "green"))
        print(colored(f"Updated: {stats['updated']}", "green"))
        print(colored(f"Skipped: {stats['skipped']}", "cyan"))
        print(colored(f"Failed: {stats['failed']}", "red"))
        
        return stats 
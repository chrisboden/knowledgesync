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
import hashlib

# LLM Configuration - override these values as needed
LLM_API_KEY_ENV_VAR = 'OPENROUTER_API_KEY'  # Environment variable name for API key
LLM_BASE_URL_ENV_VAR = 'OPENROUTER_BASE_URL'  # Environment variable name for base URL
LLM_MODEL = 'google/gemini-2.0-flash-001'  # Default model to use
LLM_DEFAULT_BASE_URL = 'https://openrouter.ai/api/v1'  # Default base URL if not specified

class SpreadsheetMetadataOperations:
    def __init__(self, base_dir: str):
        """Initialize metadata operations."""
        self.base_dir = Path(base_dir)
        self.spreadsheets_dir = self.base_dir / "spreadsheets"
        self.manifest_path = self.spreadsheets_dir / "@manifest.json"
        self.prompt_template_path = Path("prompts/extract_spreadsheet_metadata.md")
        
        # Load environment variables
        load_dotenv()
        
        # Configure OpenAI client for LLM API
        api_key = os.getenv(LLM_API_KEY_ENV_VAR)
        base_url = os.getenv(LLM_BASE_URL_ENV_VAR, LLM_DEFAULT_BASE_URL)
        
        if not api_key:
            print(colored(f"✗ Missing LLM API key. Check {LLM_API_KEY_ENV_VAR} in .env", "red"))
            return
            
        print(colored("✓ LLM configuration loaded", "green"))
        
        # Initialize OpenAI client with LLM configuration
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/chrisboden/knowledgesync",
                "X-Title": "Knowledge Sync"
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
            
    def _save_manifest(self, manifest):
        """Save the current manifest to file."""
        try:
            self.manifest_path.write_text(json.dumps(manifest, indent=2))
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
            
    def _get_content_hash(self, csv_files):
        """Calculate a hash of all CSV files' content."""
        content = ""
        for csv_file in sorted(csv_files):  # Sort to ensure consistent order
            try:
                content += csv_file.read_text(encoding='utf-8')
            except Exception as e:
                print(colored(f"✗ Error reading {csv_file.name}: {str(e)}", "red"))
                continue
        return hashlib.md5(content.encode('utf-8')).hexdigest()

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
            
            print(colored("Calling LLM API...", "cyan"))
            
            # Call LLM API via OpenAI client
            completion = await self.client.chat.completions.create(
                model=LLM_MODEL,
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
            
    async def update_manifest(self, force=False):
        """Update the manifest with metadata for all spreadsheets."""
        print(colored("\nUpdating spreadsheet metadata...", "cyan"))
        
        # Get list of spreadsheet directories
        spreadsheet_dirs = [d for d in self.spreadsheets_dir.iterdir() if d.is_dir()]
        print(colored(f"Found {len(spreadsheet_dirs)} spreadsheets", "cyan"))
        
        stats = {"added": 0, "updated": 0, "skipped": 0, "failed": 0}
        
        # Load current manifest
        manifest = self._load_manifest()
        
        # Process each spreadsheet directory
        for sheet_dir in spreadsheet_dirs:
            try:
                # Get list of CSV files in this directory
                csv_files = list(sheet_dir.glob("*.csv"))
                if not csv_files:
                    continue
                    
                # Calculate content hash for all CSV files
                current_hash = self._get_content_hash(csv_files)
                
                # Find existing entry
                existing_entry = next(
                    (entry for entry in manifest if entry["title"] == sheet_dir.name),
                    None
                )
                
                # Process spreadsheet if:
                # 1. Force refresh is enabled, OR
                # 2. No existing entry exists, OR
                # 3. Content has changed (different hash)
                if force or not existing_entry or ("contentHash" not in existing_entry) or (existing_entry["contentHash"] != current_hash):
                    # Extract metadata
                    metadata = await self.extract_metadata(sheet_dir)
                    if metadata:
                        # Add content hash
                        metadata["contentHash"] = current_hash
                        
                        if existing_entry:
                            # Update existing entry
                            existing_idx = manifest.index(existing_entry)
                            manifest[existing_idx] = metadata
                            print(colored(f"↻ Updated metadata for {sheet_dir.name}", "green"))
                            stats["updated"] += 1
                        else:
                            # Add new entry
                            manifest.append(metadata)
                            print(colored(f"+ Added metadata for {sheet_dir.name}", "green"))
                            stats["added"] += 1
                    else:
                        print(colored(f"✗ Failed to extract metadata for {sheet_dir.name}", "red"))
                        stats["failed"] += 1
                else:
                    print(colored(f"↷ Skipping {sheet_dir.name} (up to date)", "cyan"))
                    stats["skipped"] += 1
                    
            except Exception as e:
                print(colored(f"✗ Error processing {sheet_dir.name}: {str(e)}", "red"))
                stats["failed"] += 1
                
        # Save updated manifest
        self._save_manifest(manifest)
        
        # Print summary
        print("\nSpreadsheet Metadata Update Summary:")
        print(f"Added: {stats['added']}")
        print(f"Updated: {stats['updated']}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Failed: {stats['failed']}")
        
        return stats 
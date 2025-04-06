"""
Metadata operations for document analysis and manifest management.
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
import glob
import hashlib

# LLM Configuration - override these values as needed
LLM_API_KEY_ENV_VAR = 'OPENROUTER_API_KEY'  # Environment variable name for API key
LLM_BASE_URL_ENV_VAR = 'OPENROUTER_BASE_URL'  # Environment variable name for base URL
LLM_MODEL = 'google/gemini-2.0-flash-001'  # Default model to use
LLM_DEFAULT_BASE_URL = 'https://openrouter.ai/api/v1'  # Default base URL if not specified

class DocumentMetadataOperations:
    def __init__(self, base_dir: str):
        """Initialize metadata operations for documents."""
        self.base_dir = Path(base_dir)
        self.manifest_path = self.base_dir / "@manifest.json"
        self.prompt_template_path = Path("prompts/extract_document_metadata.md")
        
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
        
        # Clean up any double extensions before processing
        self._cleanup_double_extensions()
        
    def _load_manifest(self):
        """Load the current manifest file."""
        try:
            return json.loads(self.manifest_path.read_text())
        except json.JSONDecodeError:
            print(colored("✗ Invalid manifest file. Resetting to empty list.", "red"))
            return []
            
    def _save_manifest(self):
        """Save the current manifest to file."""
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2))
        
    def _get_prompt_template(self):
        """Load the metadata extraction prompt template."""
        try:
            return self.prompt_template_path.read_text()
        except FileNotFoundError:
            print(colored(f"✗ Prompt template not found at {self.prompt_template_path}", "red"))
            return None
        
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate a hash of the file's content."""
        content = file_path.read_text(encoding='utf-8')
        return hashlib.md5(content.encode('utf-8')).hexdigest()
        
    async def extract_metadata(self, file_path: Path):
        """Extract metadata from a single file using AI."""
        try:
            print(colored(f"\nExtracting metadata for {file_path.name}...", "cyan"))
            
            # Read file contents
            file_contents = file_path.read_text()
            
            # Get and check prompt template
            prompt_template = self._get_prompt_template()
            if not prompt_template:
                return None
                
            # Prepare prompt
            prompt = prompt_template.format(
                file_name=file_path.name,
                file_contents=file_contents
            )
            
            print(colored("Calling LLM API...", "cyan"))
            
            # Create a default metadata structure
            default_metadata = {
                "id": f"doc_{hash(file_path.name)}",
                "title": file_path.stem,
                "fileName": file_path.name,
                "localPath": str(file_path.absolute()),  # Always use absolute path
                "createdAt": datetime.fromtimestamp(file_path.stat().st_ctime).isoformat(),
                "updatedAt": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                "summary": "",
                "wordCount": len(file_contents.split()),
                "source": "Google Docs",
                "language": "en",
                "primaryTopics": [],
                "questionTypes": [],
                "useCases": [],
                "audience": "general",
                "documentSections": []
            }
            
            # Call LLM API via OpenAI client
            completion = await self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "You are a Document Metadata Extraction Assistant."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            print(colored("Parsing API response...", "cyan"))
            # Get response content
            content = completion.choices[0].message.content
            print(colored(f"Raw response: {content}", "yellow"))
            
            # Parse JSON response
            try:
                metadata = json.loads(content)
                if isinstance(metadata, list) and len(metadata) > 0:
                    metadata = metadata[0]
                elif "metadata" in metadata and isinstance(metadata["metadata"], list):
                    metadata = metadata["metadata"][0]  # Handle nested metadata
                
                # Always ensure absolute path, regardless of what the LLM returns
                metadata["localPath"] = str(file_path.absolute())
                
                # Merge with default metadata
                default_metadata.update(metadata)
                metadata = default_metadata
                
            except (json.JSONDecodeError, IndexError) as e:
                print(colored(f"Error parsing response: {str(e)}", "red"))
                metadata = default_metadata
            
            print(colored("✓ Metadata extracted successfully", "green"))
            return metadata
            
        except Exception as e:
            print(colored(f"✗ Error in metadata extraction: {str(e)}", "red"))
            if 'completion' in locals():
                print(colored(f"Response debug info: {completion}", "yellow"))
            return None
            
    async def update_manifest(self, force=False):
        """Update the manifest with metadata for all files."""
        print(colored("\nUpdating document metadata...", "cyan"))
        
        md_files = list(self.base_dir.glob("*.md"))
        print(colored(f"Found {len(md_files)} markdown files", "cyan"))
        
        # Clean up manifest entries
        cleaned_manifest = []
        for entry in self.manifest:
            # Fix double .md extensions
            filename = entry["fileName"]
            if filename.lower().endswith('.md.md'):
                entry["fileName"] = filename[:-3]  # Remove one .md
            
            # Fix incorrect localPath values
            if entry["localPath"] in ["./", ".", "/path/to/documents", "/path/to/your/documents"] or not entry["localPath"].startswith("/"):
                # Find the actual file in md_files
                matching_file = next(
                    (f for f in md_files if f.name == entry["fileName"]),
                    None
                )
                if matching_file:
                    entry["localPath"] = str(matching_file.absolute())
            
            cleaned_manifest.append(entry)
        self.manifest = cleaned_manifest
        
        stats = {"added": 0, "updated": 0, "failed": 0, "skipped": 0}
        tasks = []
        files_to_process = []
        
        for file_path in md_files:
            current_hash = self._get_file_hash(file_path)
            
            # Find existing entry
            existing_entry = next(
                (entry for entry in self.manifest if entry["fileName"] == file_path.name),
                None
            )
            
            # Process file if:
            # 1. Force refresh is enabled, OR
            # 2. No existing entry exists, OR
            # 3. Content has changed (different hash)
            if force or not existing_entry or ("contentHash" not in existing_entry) or (existing_entry["contentHash"] != current_hash):
                files_to_process.append(file_path)
                tasks.append(self.extract_metadata(file_path))
            else:
                print(colored(f"↷ Skipping {file_path.name} (content unchanged)", "cyan"))
                stats["skipped"] += 1
                
        if tasks:
            # Process files in parallel
            results = await asyncio.gather(*tasks)
            
            # Update manifest with results
            for file_path, metadata in zip(files_to_process, results):
                if metadata:
                    # Add content hash
                    metadata["contentHash"] = self._get_file_hash(file_path)
                    
                    # Update or add to manifest
                    existing_idx = next(
                        (i for i, entry in enumerate(self.manifest) if entry["fileName"] == file_path.name),
                        None
                    )
                    
                    if existing_idx is not None:
                        self.manifest[existing_idx] = metadata
                        print(colored(f"↻ Updated metadata for {file_path.name}", "green"))
                        stats["updated"] += 1
                    else:
                        self.manifest.append(metadata)
                        print(colored(f"+ Added metadata for {file_path.name}", "green"))
                        stats["added"] += 1
                else:
                    print(colored(f"✗ Failed to extract metadata for {file_path.name}", "red"))
                    stats["failed"] += 1
                    
            # Save updated manifest
            self._save_manifest()
            
        # Print summary
        print("\nMetadata Update Summary:")
        print(f"Added: {stats['added']}")
        print(f"Updated: {stats['updated']}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Failed: {stats['failed']}")
        
        return stats

    def _cleanup_double_extensions(self):
        """Clean up any files with double .md extensions."""
        for file_path in self.base_dir.glob("*.md.md"):
            try:
                correct_path = file_path.with_name(file_path.stem)  # Removes one .md
                file_path.rename(correct_path)
                print(colored(f"✓ Fixed double extension: {file_path.name} -> {correct_path.name}", "green"))
            except Exception as e:
                print(colored(f"✗ Error fixing double extension for {file_path.name}: {str(e)}", "red")) 
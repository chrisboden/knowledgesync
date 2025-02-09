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

class DocumentMetadataOperations:
    def __init__(self, base_dir: str):
        """Initialize metadata operations for documents."""
        self.base_dir = Path(base_dir)
        self.manifest_path = self.base_dir / "@manifest.json"
        self.prompt_template_path = Path("prompts/extract_document_metadata.md")
        
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
            
            print(colored("Calling OpenRouter API...", "cyan"))
            
            # Create a default metadata structure
            default_metadata = {
                "id": f"doc_{hash(file_path.name)}",
                "title": file_path.stem,
                "fileName": file_path.name,
                "localPath": str(self.base_dir),  # Use actual base directory
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
            
            # Call OpenRouter API via OpenAI client
            completion = await self.client.chat.completions.create(
                model="google/gemini-2.0-flash-001",
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
            
    async def update_manifest(self):
        """Update the manifest with metadata for all files."""
        print(colored("\nUpdating document metadata...", "cyan"))
        
        md_files = list(self.base_dir.glob("*.md"))
        print(colored(f"Found {len(md_files)} markdown files", "cyan"))
        
        # Clean up manifest entries with incorrect double .md extensions
        cleaned_manifest = []
        for entry in self.manifest:
            filename = entry["fileName"]
            if filename.lower().endswith('.md.md'):
                entry["fileName"] = filename[:-3]  # Remove one .md
            cleaned_manifest.append(entry)
        self.manifest = cleaned_manifest
        
        stats = {"added": 0, "updated": 0, "failed": 0, "skipped": 0}
        tasks = []
        files_to_process = []
        
        for file_path in md_files:
            current_hash = self._get_file_hash(file_path)
            
            # Find existing entry in manifest
            existing_entry = next(
                (item for item in self.manifest if item["fileName"] == file_path.name),
                None
            )
            
            needs_metadata = False
            
            if not existing_entry:
                # New file, needs metadata
                print(colored(f"+ New file detected: {file_path.name}", "green"))
                needs_metadata = True
            else:
                # Check if existing entry has metadata and content hash
                has_metadata = all(key in existing_entry for key in ["summary", "primaryTopics", "documentSections"])
                stored_hash = existing_entry.get("contentHash")
                
                if not has_metadata:
                    print(colored(f"⟳ Missing metadata for {file_path.name}", "yellow"))
                    needs_metadata = True
                elif not stored_hash:
                    print(colored(f"⟳ Missing content hash for {file_path.name}", "yellow"))
                    needs_metadata = True
                elif stored_hash != current_hash:
                    print(colored(f"⟳ Content changed: {file_path.name}", "yellow"))
                    print(colored(f"   Previous hash: {stored_hash}", "yellow"))
                    print(colored(f"   Current hash: {current_hash}", "yellow"))
                    needs_metadata = True
                else:
                    print(colored(f"↷ Skipping metadata for {file_path.name} (content unchanged)", "cyan"))
                    stats["skipped"] += 1
            
            if needs_metadata:
                tasks.append(self.extract_metadata(file_path))
                files_to_process.append((file_path, current_hash))
        
        # Process files in parallel if there are any that need updating
        if tasks:
            results = await asyncio.gather(*tasks)
            
            # Process results and update manifest
            for i, metadata in enumerate(results):
                file_path, current_hash = files_to_process[i]
                if metadata:
                    # Add content hash to metadata
                    metadata["contentHash"] = current_hash
                    
                    # Update timestamps
                    for ts_field in ["createdAt", "updatedAt"]:
                        if ts_field in metadata:
                            try:
                                ts = datetime.fromisoformat(metadata[ts_field])
                                if not ts.tzinfo:
                                    ts = ts.replace(tzinfo=pytz.UTC)
                                metadata[ts_field] = ts.isoformat()
                            except (ValueError, TypeError):
                                metadata[ts_field] = datetime.now(pytz.UTC).isoformat()
                    
                    existing_entry = next(
                        (item for item in self.manifest if item["fileName"] == file_path.name),
                        None
                    )
                    
                    if existing_entry:
                        # Update existing entry
                        self.manifest = [
                            metadata if item["fileName"] == file_path.name else item
                            for item in self.manifest
                        ]
                        print(colored(f"↻ Updated metadata for {file_path.name}", "green"))
                        stats["updated"] += 1
                    else:
                        # Add new entry
                        self.manifest.append(metadata)
                        print(colored(f"+ Added metadata for {file_path.name}", "green"))
                        stats["added"] += 1
                    
                    # Save manifest after each successful update
                    self._save_manifest()
                else:
                    print(colored(f"✗ Failed to extract metadata for {file_path.name}", "red"))
                    stats["failed"] += 1
        
        # Print summary
        print("\nMetadata Update Summary:")
        print(colored(f"Added: {stats['added']}", "green"))
        print(colored(f"Updated: {stats['updated']}", "green"))
        print(colored(f"Skipped: {stats['skipped']}", "cyan"))
        print(colored(f"Failed: {stats['failed']}", "red"))
        
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

async def update_document_metadata(docs_dir: str, manifest_data: list):
    """Update metadata for documents that need it based on specific criteria."""
    print("\nUpdating document metadata...")
    
    # Load OpenRouter configuration
    if not load_openrouter_config():
        return
    
    markdown_files = glob.glob(os.path.join(docs_dir, "*.md"))
    print(f"Found {len(markdown_files)} markdown files")
    
    files_to_update = []
    for file_path in markdown_files:
        file_name = os.path.basename(file_path)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
        
        # Find existing manifest entry
        existing_doc = next((doc for doc in manifest_data if doc.get("fileName") == file_name), None)
        
        needs_update = False
        if not existing_doc:
            print(f"+ New file found: {file_name}")
            needs_update = True
        elif not existing_doc.get("metadata"):
            print(f"⚠ No metadata found for: {file_name}")
            needs_update = True
        else:
            # Convert last_synced to datetime for comparison
            last_synced = datetime.fromisoformat(existing_doc.get("last_synced", "1970-01-01T00:00:00+00:00"))
            if file_mtime > last_synced:
                print(f"⟳ File modified: {file_name}")
                print(f"   Previous update: {last_synced}")
                print(f"   Current mtime: {file_mtime}")
                needs_update = True
            else:
                print(f"↷ Skipping metadata for {file_name}")
                print(f"   Last updated: {last_synced}")
                continue
        
        if needs_update:
            files_to_update.append(file_path)
    
    # Process files that need updating
    updated_count = 0
    skipped_count = len(markdown_files) - len(files_to_update)
    failed_count = 0
    
    for file_path in files_to_update:
        try:
            file_name = os.path.basename(file_path)
            print(f"\nExtracting metadata for {file_name}...")
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            metadata = await extract_metadata_from_content(content, file_name)
            if metadata:
                # Update or add to manifest
                doc_index = next((i for i, doc in enumerate(manifest_data) 
                                if doc.get("fileName") == file_name), None)
                
                if doc_index is not None:
                    manifest_data[doc_index].update(metadata)
                    manifest_data[doc_index]["last_synced"] = datetime.now(timezone.utc).isoformat()
                else:
                    metadata["last_synced"] = datetime.now(timezone.utc).isoformat()
                    manifest_data.append(metadata)
                
                updated_count += 1
                print(f"✓ Metadata extracted successfully")
            else:
                failed_count += 1
                print(f"✗ Failed to extract metadata")
                
        except Exception as e:
            failed_count += 1
            print(f"✗ Error processing {file_name}: {str(e)}")
    
    # Save updated manifest
    manifest_path = os.path.join(docs_dir, "@manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)
    
    print(f"\nMetadata Update Summary:")
    print(f"Added/Updated: {updated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}") 
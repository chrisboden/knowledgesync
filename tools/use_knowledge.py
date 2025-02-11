"""
Tool for selecting and using relevant documents and spreadsheets from a knowledge base.

See use_knowledge.json for tool metadata and usage information.
"""
# Configuration - override these values as needed
DESTINATION_FOLDER = None  # If None, will use DESTINATION_FOLDER from .env file

import json
import os
import shutil
import csv
from pathlib import Path
from typing import List, Dict, Union
from termcolor import colored
from openai import AsyncOpenAI
from dotenv import load_dotenv

class KnowledgeOperations:
    def __init__(self):
        """Initialize KnowledgeOperations with path from environment."""
        # Load environment variables
        load_dotenv()
        
        # Get base directory from configuration or environment
        base_dir = DESTINATION_FOLDER or os.getenv('DESTINATION_FOLDER')
        if not base_dir:
            raise ValueError("DESTINATION_FOLDER not found in configuration or environment variables")
            
        self.base_dir = Path(base_dir)
        
        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            base_url=os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1'),
            api_key=os.getenv('OPENROUTER_API_KEY'),
            default_headers={
                "HTTP-Referer": "https://github.com/OpenRouterTeam/openrouter-python",
                "X-Title": "Knowledge Base Tool"
            }
        )
        
        if not self.client.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")
        
        # Clean up any existing knowledge base files
        self._cleanup_temp_files()
    
    def _cleanup_temp_files(self):
        """Remove any existing temporary knowledge base files."""
        temp_dir = Path("temp")
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                print(colored("✓ Cleaned up existing temporary files", "green"))
            except Exception as e:
                print(colored(f"Warning: Failed to clean up temporary files: {str(e)}", "yellow"))
    
    def _extract_json_from_response(self, content: str) -> str:
        """Extract JSON content from a response that might be wrapped in markdown code blocks."""
        # If response contains ```json, extract content between backticks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return content.strip()
    
    def _load_manifests(self) -> Dict[str, List]:
        """Load document and spreadsheet manifests from all folders."""
        manifests = {
            "documents": [],
            "spreadsheets": []
        }
        
        # Iterate through all subdirectories in the base directory
        for folder_path in self.base_dir.iterdir():
            if not folder_path.is_dir():
                continue
                
            docs_manifest = folder_path / "documents" / "@manifest.json"
            sheets_manifest = folder_path / "spreadsheets" / "@manifest.json"
            
            try:
                if docs_manifest.exists():
                    folder_docs = json.loads(docs_manifest.read_text())
                    # Add folder name to each document's metadata
                    for doc in folder_docs:
                        doc["folder"] = folder_path.name
                    manifests["documents"].extend(folder_docs)
                    print(colored(f"✓ Loaded manifest entries for {len(folder_docs)} documents from {folder_path.name}", "green"))
            except Exception as e:
                print(colored(f"Warning: Failed to load documents manifest from {folder_path.name}: {str(e)}", "yellow"))
                
            try:
                if sheets_manifest.exists():
                    folder_sheets = json.loads(sheets_manifest.read_text())
                    # Add folder name to each spreadsheet's metadata
                    for sheet in folder_sheets:
                        sheet["folder"] = folder_path.name
                    manifests["spreadsheets"].extend(folder_sheets)
                    print(colored(f"✓ Loaded manifest entries for {len(folder_sheets)} spreadsheets from {folder_path.name}", "green"))
            except Exception as e:
                print(colored(f"Warning: Failed to load spreadsheets manifest from {folder_path.name}: {str(e)}", "yellow"))
                
        return manifests

    def _format_csv_as_markdown(self, csv_path: Path) -> str:
        """Convert CSV content to a markdown table."""
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            if not rows:
                return ""
                
            # Create header
            markdown = "| " + " | ".join(rows[0]) + " |\n"
            # Add separator
            markdown += "| " + " | ".join(["---" for _ in rows[0]]) + " |\n"
            # Add data rows
            for row in rows[1:]:
                markdown += "| " + " | ".join(row) + " |\n"
                
            return markdown
        except Exception as e:
            print(colored(f"Warning: Failed to format CSV {csv_path}: {str(e)}", "yellow"))
            return ""

    async def select_relevant_docs(self, user_input: str) -> List[Dict[str, str]]:
        """
        Use LLM to analyze manifests and select relevant documents and spreadsheets.
        Returns list of dicts with file paths and selection rationales.
        """
        try:
            # Read manifests
            manifests = self._load_manifests()
            if not manifests["documents"] and not manifests["spreadsheets"]:
                raise FileNotFoundError("No manifests found")
            
            # Prepare prompt for content selection
            prompt = f"""Given the following user input and content metadata, select the most relevant documents and spreadsheets that would help address the user's needs.
            Analyze each item's summary, topics, and other metadata to make informed selections.
            
            User Input: {user_input}
            
            Available Content:
            
            Documents:
            {json.dumps(manifests["documents"], indent=2)}
            
            Spreadsheets:
            {json.dumps(manifests["spreadsheets"], indent=2)}
            
            Return a JSON array of selected content in this format:
            [
                {{
                    "type": "document|spreadsheet",
                    "folder": "folder_name",  // The folder containing the file
                    "file": "relative/path/to/file",  // For spreadsheets, just use the spreadsheet name
                    "worksheets": ["sheet1", "sheet2"],  // Only for spreadsheets
                    "rationale": "explanation of why this content was selected"
                }}
            ]
            
            For documents, include the path relative to the documents directory.
            For spreadsheets, just use the spreadsheet name (e.g. "Tokenizer Plan").
            Select only the most relevant content. Explain your rationale clearly but concisely.
            Return ONLY the JSON array, no other text."""
            
            # Call OpenRouter API for content selection
            response = await self.client.chat.completions.create(
                model="google/gemini-2.0-flash-001",
                messages=[
                    {"role": "system", "content": "You are a content selection assistant. Analyze content metadata and select the most relevant items for the given task. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            # Parse response
            content = response.choices[0].message.content.strip()
            print(colored("\nLLM Response:", "cyan"))
            print(content)
            
            # Extract and parse JSON
            json_content = self._extract_json_from_response(content)
            selected_content = json.loads(json_content)
            
            # Validate selected content exists
            validated_content = []
            for item in selected_content:
                folder_path = self.base_dir / item["folder"]
                if item["type"] == "document":
                    file_path = folder_path / "documents" / item["file"]
                    if file_path.exists():
                        validated_content.append(item)
                    else:
                        print(colored(f"Warning: Selected document not found: {item['folder']}/{item['file']}", "yellow"))
                elif item["type"] == "spreadsheet":
                    sheet_dir = folder_path / "spreadsheets" / item["file"]
                    if sheet_dir.exists():
                        # Validate worksheets exist
                        valid_worksheets = []
                        for worksheet in item.get("worksheets", []):
                            csv_path = sheet_dir / f"{worksheet}.csv"
                            if csv_path.exists():
                                valid_worksheets.append(worksheet)
                            else:
                                print(colored(f"Warning: Worksheet not found: {item['folder']}/{item['file']}/{worksheet}", "yellow"))
                        if valid_worksheets:
                            item["worksheets"] = valid_worksheets
                            validated_content.append(item)
                    else:
                        print(colored(f"Warning: Selected spreadsheet not found: {item['folder']}/{item['file']}", "yellow"))
            
            return validated_content
            
        except Exception as e:
            print(colored(f"Error selecting content: {str(e)}", "red"))
            print(colored("Full error:", "red"))
            import traceback
            print(traceback.format_exc())
            return []
    
    def create_knowledge_base(self, selected_content: List[Dict[str, str]]) -> str:
        """
        Create a temporary knowledge base file from selected documents and spreadsheets.
        Returns path to the created knowledge base file.
        """
        try:
            # Create temp directory if it doesn't exist
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            
            # Create knowledge base file
            kb_path = temp_dir / "knowledge_base.md"
            
            with kb_path.open('w', encoding='utf-8') as kb_file:
                for i, item in enumerate(selected_content):
                    # Write separator between items
                    if i > 0:
                        kb_file.write("\n\n" + "="*80 + "\n\n")
                    
                    # Write metadata
                    kb_file.write(f"Type: {item['type'].capitalize()}\n")
                    kb_file.write(f"Folder: {item['folder']}\n")
                    kb_file.write(f"Source: {item['file']}\n")
                    kb_file.write(f"Selection Rationale: {item['rationale']}\n\n")
                    kb_file.write("-"*40 + "\n\n")
                    
                    # Write content based on type
                    if item["type"] == "document":
                        file_path = self.base_dir / item["folder"] / "documents" / item["file"]
                        kb_file.write(file_path.read_text(encoding='utf-8'))
                    else:  # spreadsheet
                        sheet_dir = self.base_dir / item["folder"] / "spreadsheets" / item["file"]
                        for worksheet in item.get("worksheets", []):
                            csv_path = sheet_dir / f"{worksheet}.csv"
                            kb_file.write(f"\n### Worksheet: {worksheet}\n\n")
                            markdown_table = self._format_csv_as_markdown(csv_path)
                            kb_file.write(markdown_table)
                            kb_file.write("\n")
            
            return str(kb_path)
            
        except Exception as e:
            print(colored(f"Error creating knowledge base: {str(e)}", "red"))
            return ""

async def execute(query: str) -> dict:
    """
    Execute the use_knowledge tool.
    
    Parameters:
        query (str): The user's query or task description
        
    Returns:
        dict: A dictionary containing the result (path to knowledge base) and any follow-on instructions
    """
    try:
        knowledge_ops = KnowledgeOperations()
        
        # Step 1: Select relevant documents
        print(colored("Selecting relevant documents...", "cyan"))
        selected_content = await knowledge_ops.select_relevant_docs(query)
        
        if not selected_content:
            return {
                "result": "",
                "follow_on_instructions": ["No relevant documents found for the query."]
            }
            
        # Print selection results
        print("\nSelected documents:")
        for item in selected_content:
            print(colored(f"\n• {item['folder']}/{item['file']}", "green"))
            print(f"  Rationale: {item['rationale']}")
        
        # Step 2: Create knowledge base
        print(colored("\nCreating knowledge base...", "cyan"))
        kb_path = knowledge_ops.create_knowledge_base(selected_content)
        
        if kb_path:
            print(colored(f"\nKnowledge base created: {kb_path}", "green"))
            return {
                "result": kb_path,
                "follow_on_instructions": [
                    f"Knowledge base created at {kb_path}",
                    f"Selected {len(selected_content)} relevant documents"
                ]
            }
        else:
            return {
                "result": "",
                "follow_on_instructions": ["Failed to create knowledge base."]
            }
        
    except Exception as e:
        print(colored(f"Error using knowledge tool: {str(e)}", "red"))
        return {
            "result": "",
            "follow_on_instructions": [f"Error: {str(e)}"]
        }

# Tool metadata following the required format
TOOL_METADATA = {
    "type": "function",
    "function": {
        "name": "use_knowledge",
        "description": "Selects relevant documents and spreadsheets from a knowledge base based on a query and combines them into a single file",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's query or task description"
                }
            },
            "required": ["query"]
        }
    }
}


if __name__ == "__main__":
    import sys
    
    # Get query from command line argument, or use test query if none provided
    query = sys.argv[1] if len(sys.argv) > 1 else "What are the key features of the Tokenizer program?"
    print(colored(f"\nQuerying knowledge base: {query}", "cyan"))
    
    import asyncio
    result = asyncio.run(execute(query=query))
    
    print("\nTool execution result:")
    print(colored("Result:", "green"), result["result"])
    print(colored("Follow-on instructions:", "yellow"))
    for instruction in result["follow_on_instructions"]:
        print(f"- {instruction}")
    
    if result["result"]:
        # Display first few lines of the knowledge base
        try:
            with open(result["result"], 'r') as f:
                print("\nFirst few lines of knowledge base:")
                print("-" * 40)
                for i, line in enumerate(f):
                    if i < 10:  # Show first 10 lines
                        print(line.rstrip())
                    else:
                        print("...")
                        break
        except Exception as e:
            print(colored(f"Error reading knowledge base: {str(e)}", "red")) 
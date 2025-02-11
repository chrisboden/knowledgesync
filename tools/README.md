# Knowledge Base Tool

This tool helps you query and extract relevant information from a synchronized Google Docs/Sheets knowledge base. It uses AI to select the most relevant documents and spreadsheets based on your query, combining them into a single markdown file for easy reference.

## Features

- AI-powered document selection based on semantic relevance
- Support for both documents and spreadsheets
- Multi-folder knowledge base support
- Automatic CSV to markdown table conversion
- Rich metadata inclusion
- Clean temporary file management
- Colored console output for better visibility

## Setup

1. Ensure you have the main sync utility set up and running (see main README)

2. Configure environment variables in your `.env` file:
   ```bash
   # Required for the knowledge base tool
   DESTINATION_FOLDER=/path/to/your/synced/files
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   OPENROUTER_API_KEY=your_openrouter_api_key
   ```

## Usage

### Command Line
```bash
python use_knowledge.py "your query here"
```

Example:
```bash
python use_knowledge.py "What are the key features of the Tokenizer program?"
```

### As a Python Module
```python
from tools.use_knowledge import execute
import asyncio

# Run the query
result = asyncio.run(execute(query="your query here"))

# Access results
knowledge_base_path = result["result"]
instructions = result["follow_on_instructions"]
```

## Output

The tool creates a knowledge base file in the `temp` directory containing:

1. Selected Document Metadata:
   - Type (Document/Spreadsheet)
   - Source Folder
   - File Name
   - Selection Rationale

2. Document Content:
   - Full text of selected documents
   - Formatted markdown tables for spreadsheets
   - Clear separators between different sources

## Example Output Structure

```markdown
Type: Document
Folder: knowledge
Source: about_project.md
Selection Rationale: Contains overview of project goals and features

----------------------------------------

[Document content here]

================================================================================

Type: Spreadsheet
Folder: projects
Source: Metrics Dashboard
Selection Rationale: Contains relevant performance metrics

----------------------------------------

### Worksheet: Overview

| Metric | Value | Target |
|--------|--------|--------|
| ... | ... | ... |
```

## Error Handling

The tool includes robust error handling for:
- Missing environment variables
- Invalid file paths
- API failures
- JSON parsing errors
- File read/write errors

## Dependencies

Required Python packages:
- openai
- python-dotenv
- termcolor
- pathlib

## Notes

- Temporary files are automatically cleaned up between runs
- The tool supports multiple Google Drive folders
- Spreadsheets are converted to markdown tables for better readability
- The knowledge base includes metadata about why each document was selected
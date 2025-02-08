"""
Google Drive operations for the Docs to Markdown sync utility.
"""
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import pickle
import re
from termcolor import colored

# If modifying these scopes, delete the token.pickle file.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class DriveOperations:
    def __init__(self):
        """Initialize the Drive API client."""
        self.creds = None
        self.service = None
        
    def authenticate(self):
        """Authenticate with Google Drive API."""
        try:
            # Check if we have valid credentials
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    self.creds = pickle.load(token)
            
            # If no valid credentials, let user log in
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    self.creds = flow.run_local_server(port=0)
                
                # Save credentials for future use
                with open('token.pickle', 'wb') as token:
                    pickle.dump(self.creds, token)
            
            self.service = build('drive', 'v3', credentials=self.creds)
            print(colored("✓ Successfully authenticated with Google Drive", "green"))
            return True
            
        except Exception as e:
            print(colored(f"✗ Authentication failed: {str(e)}", "red"))
            return False

    def list_docs_in_folder(self, folder_id):
        """List all Google Docs in the specified folder."""
        try:
            query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
            results = self.service.files().list(
                q=query,
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            files = results.get('files', [])
            print(colored(f"✓ Found {len(files)} Google Docs in folder", "green"))
            return files
            
        except HttpError as e:
            print(colored(f"✗ Error listing files: {str(e)}", "red"))
            return []

    def _clean_image_references(self, markdown_content):
        """
        Clean image references in markdown content.
        Replace base64 data with a simple reference to the image number.
        """
        # Counter for image references
        image_count = 1
        
        # Function to replace base64 data with simple reference
        def replace_base64(match):
            nonlocal image_count
            ref_name = f"image{image_count}"
            image_count += 1
            return f"[{ref_name}]: <image_reference_{ref_name}>"
        
        # Pattern to match image references with base64 data
        pattern = r'\[image\d+\]: <data:image/[^>]+>'
        
        # Replace all base64 image data with simple references
        cleaned_content = re.sub(pattern, replace_base64, markdown_content)
        
        return cleaned_content

    def export_doc_to_markdown(self, file_id):
        """Export a Google Doc to Markdown format."""
        try:
            # Use the Drive API's files().export() method
            request = self.service.files().export(
                fileId=file_id,
                mimeType='text/markdown'
            ).execute()
            
            if request:
                # Convert to string if needed
                content = request.decode('utf-8') if isinstance(request, bytes) else request
                
                # Clean image references
                cleaned_content = self._clean_image_references(content)
                
                return cleaned_content
            else:
                print(colored(f"✗ Export failed - no content returned", "red"))
                return None
                
        except Exception as e:
            print(colored(f"✗ Error exporting document: {str(e)}", "red"))
            return None

    def get_file_metadata(self, file_id):
        """Get metadata for a specific file."""
        try:
            return self.service.files().get(
                fileId=file_id,
                fields='name,modifiedTime'
            ).execute()
        except HttpError as e:
            print(colored(f"✗ Error getting file metadata: {str(e)}", "red"))
            return None 
"""
Google Sheets operations for the sync utility.
Handles conversion of Google Sheets to CSV files.
"""
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import csv
from pathlib import Path
from datetime import datetime
import pytz
from termcolor import colored

class SheetsOperations:
    def __init__(self, base_dir: str):
        """Initialize the Sheets API client."""
        self.base_dir = Path(base_dir)
        self.sheets_dir = self.base_dir / "spreadsheets"
        self.sheets_dir.mkdir(parents=True, exist_ok=True)
        self.service = None
        self.drive_service = None
        
    def authenticate(self, credentials):
        """Authenticate with Google Sheets API using existing credentials."""
        try:
            self.service = build('sheets', 'v4', credentials=credentials)
            self.drive_service = build('drive', 'v3', credentials=credentials)
            print(colored("✓ Successfully authenticated with Google Sheets", "green"))
            return True
        except Exception as e:
            print(colored(f"✗ Sheets authentication failed: {str(e)}", "red"))
            return False

    def list_sheets_in_folder(self, folder_id):
        """List all Google Sheets in the specified folder."""
        try:
            # Use Drive API to list sheets (mimeType for Google Sheets)
            query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            files = results.get('files', [])
            print(colored(f"✓ Found {len(files)} Google Sheets in folder", "green"))
            return files
            
        except HttpError as e:
            print(colored(f"✗ Error listing sheets: {str(e)}", "red"))
            return []

    def export_sheet_to_csv(self, sheet_id, sheet_name):
        """Export a specific sheet to CSV format."""
        try:
            # Get the sheet data
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=sheet_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                print(colored(f"✗ No data found in sheet: {sheet_name}", "yellow"))
                return None
                
            # Convert to CSV string
            output = []
            for row in values:
                # Pad row with empty strings if it's shorter than the header
                padded_row = row + [''] * (len(values[0]) - len(row))
                output.append(padded_row)
                
            return output
            
        except HttpError as e:
            print(colored(f"✗ Error exporting sheet to CSV: {str(e)}", "red"))
            return None

    def get_sheet_metadata(self, sheet_id):
        """Get metadata about a specific spreadsheet."""
        try:
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=sheet_id
            ).execute()
            
            return {
                'id': sheet_id,
                'title': sheet_metadata['properties']['title'],
                'sheets': [{
                    'name': sheet['properties']['title'],
                    'rows': sheet['properties']['gridProperties']['rowCount'],
                    'columns': sheet['properties']['gridProperties']['columnCount']
                } for sheet in sheet_metadata['sheets']]
            }
            
        except HttpError as e:
            print(colored(f"✗ Error getting sheet metadata: {str(e)}", "red"))
            return None

    def save_sheet_as_csv(self, sheet_id, metadata, sheet_data, sheet_name):
        """Save sheet data as CSV file in the appropriate directory."""
        try:
            # Create directory for this spreadsheet
            sheet_dir = self.sheets_dir / metadata['title']
            sheet_dir.mkdir(exist_ok=True)
            
            # Save CSV file
            csv_path = sheet_dir / f"{sheet_name}.csv"
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(sheet_data)
                
            return str(csv_path.relative_to(self.base_dir))
            
        except Exception as e:
            print(colored(f"✗ Error saving CSV file: {str(e)}", "red"))
            return None 
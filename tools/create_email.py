#!/usr/bin/env python3
# /tools/create_email.py
import os
import sys
import requests
from typing import List, Optional, Union
from dotenv import load_dotenv

def main():
    # Force unbuffered output
    sys.stdout.reconfigure(line_buffering=True)

# Load environment variables
load_dotenv()
    sys.stdout.write("Environment variables loaded\n")
    sys.stdout.flush()

    if len(sys.argv) != 4:
        sys.stdout.write("Usage: python create_email.py TO SUBJECT CONTENT\n")
        sys.stdout.flush()
        sys.exit(1)

    to_email = sys.argv[1]
    subject = sys.argv[2]
    content = sys.argv[3]

    # Get webhook URL
    webhook_url = os.getenv('ZAPIER_EMAIL_WEBHOOK_URL')
    if not webhook_url:
        sys.stdout.write("Error: ZAPIER_EMAIL_WEBHOOK_URL not set in environment variables\n")
        sys.stdout.flush()
        sys.exit(1)

    # Prepare payload
    payload = {
        'to': [to_email],
        'subject': subject,
        'body': content,
        'html_body': f'<p>{content.replace("\n", "<br>")}</p>',
        'from_email': 'chris.boden@noosa.qld.gov.au'
    }

    sys.stdout.write(f"Sending email to {to_email}...\n")
    sys.stdout.flush()

    try:
        response = requests.post(
            webhook_url, 
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        sys.stdout.write(f"Response status code: {response.status_code}\n")
        sys.stdout.write(f"Response text: {response.text}\n")
        sys.stdout.flush()
        
        if response.status_code == 200:
            sys.stdout.write(f"Successfully sent email: {subject}\n")
        else:
            sys.stdout.write(f"Failed to send email: {response.status_code} - {response.text}\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(f"Error sending email: {str(e)}\n")
        sys.stdout.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()

TOOL_METADATA = {
    "type": "function",
    "function": {
        "name": "email_create",
        "description": "Send an HTML email using the Hub's branded template. Perfect for sending announcements, newsletters, or any communication that should have the Hub's professional look.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}}
                    ],
                    "description": "Single email address or list of recipient email addresses"
                },
                "subject": {
                    "type": "string",
                    "description": "Subject line of the email"
                },
                "content": {
                    "type": "string",
                    "description": "The main content of the email. Can be plain text - will be automatically formatted with the Hub's styling."
                },
                "cc": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}}
                    ],
                    "description": "Optional - Single email address or list of CC recipients"
                },
                "bcc": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}}
                    ],
                    "description": "Optional - Single email address or list of BCC recipients"
                },
                "from_email": {
                    "type": "string",
                    "description": "Optional - Sender email address. Defaults to Hub's official email."
                }
            },
            "required": ["to", "subject", "content"]
        }
    }
}
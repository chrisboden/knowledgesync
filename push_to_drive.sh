#!/bin/bash
# Script to push local changes to Google Drive

# Change to the directory containing the script
cd "$(dirname "$0")"

# Run the push script
python3 push_to_drive.py

# Exit with the same status as the Python script
exit $? 
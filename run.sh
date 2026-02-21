#!/usr/bin/env bash

set -e

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt -q

# Run the migration script with all passed arguments
python migrate.py "$@"

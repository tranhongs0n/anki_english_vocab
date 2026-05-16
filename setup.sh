#!/bin/bash

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install Python 3 and pip if not installed
echo "Checking for Python 3 and pip..."
sudo apt-get install -y python3 python3-pip python3-venv

# Create a virtual environment (optional but recommended)
echo "Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install requirements
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete! To start using the scripts, remember to activate the virtual environment with:"
echo "source venv/bin/activate"

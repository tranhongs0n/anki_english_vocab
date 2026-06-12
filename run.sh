#!/bin/bash
echo "Starting Gemini WebAPI REST Server..."
cd /d/Software/gemini-api
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

echo "Waiting for API server to boot..."
sleep 3

cd - > /dev/null
echo "Starting Vocabulary Extractor Script..."
source venv/bin/activate
python script.py

# Cleanup API server process on script exit
kill $API_PID

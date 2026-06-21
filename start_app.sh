#!/bin/bash

# Get the directory of the script to ensure paths are correct regardless of where it's run from
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "================================================="
echo "🚀 Starting SRE Observability Assistant..."
echo "================================================="

echo "📦 1. Starting MySQL database (Docker)..."
docker compose up -d

echo "⚙️ 2. Starting FastAPI Backend..."
cd "$DIR/api"
source venv/bin/activate
# Run in background
fastapi dev main.py --port 8000 &
API_PID=$!

echo "🎨 3. Starting Streamlit UI..."
cd "$DIR/ui"
source venv/bin/activate
# Run in background
streamlit run app.py &
UI_PID=$!

echo "================================================="
echo "✅ All services started successfully!"
echo "📡 FastAPI backend: http://localhost:8000"
echo "🖥️ Streamlit UI:    http://localhost:8501"
echo ""
echo "🛑 Press Ctrl+C to gracefully stop all services."
echo "================================================="

# Cleanup function to kill background processes when Ctrl+C is pressed
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $UI_PID 2>/dev/null
    kill $API_PID 2>/dev/null
    echo "👋 Services stopped."
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# Wait indefinitely for background processes to finish (keeps the script running)
wait $UI_PID $API_PID

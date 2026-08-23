#!/bin/bash

PORT=${PORT:-8000}

echo "🚀 Starting FastAPI on 8000..."
uvicorn api.main:app --host 0.0.0.0 --port 8000 &

echo "🎨 Starting Streamlit on $PORT..."
export BACKEND_URL="http://localhost:8000"

streamlit run frontend/app.py \
    --server.port $PORT \
    --server.address 0.0.0.0 &

wait
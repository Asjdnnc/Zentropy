#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting Quantum Chat Setup..."

# 1. Install Python Dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# 2. Build liboqs
echo "🔨 Building liboqs C library..."
bash build_liboqs.sh

# 3. Configure .env
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env 2>/dev/null || touch .env
    
    # Defaults
    echo "SERVER_PORT=65432" >> .env
    echo "TARGET_RECEIVER_IP=127.0.0.1" >> .env
    echo "LOCAL_SERVER_URL=http://127.0.0.1" >> .env
fi

# determine lib path
BASE_DIR="$(pwd)"
if [[ "$OSTYPE" == "darwin"* ]]; then
    DYLIB_PATH="$BASE_DIR/liboqs/build/lib/liboqs.dylib"
    
    # Update .env (Mac)
    if grep -q "LIBOQS_DYLIB_PATH" .env; then
        # Replace existing line (using a temp file for compatibility)
        sed "s|LIBOQS_DYLIB_PATH=.*|LIBOQS_DYLIB_PATH=$DYLIB_PATH|g" .env > .env.tmp && mv .env.tmp .env
    else
        # Append new line
        echo "LIBOQS_DYLIB_PATH=$DYLIB_PATH" >> .env
    fi
else
    # Linux/Other
    SO_PATH="$BASE_DIR/liboqs/build/lib/liboqs.so"
    if grep -q "LIBOQS_DYLIB_PATH" .env; then
        sed "s|LIBOQS_DYLIB_PATH=.*|LIBOQS_DYLIB_PATH=$SO_PATH|g" .env > .env.tmp && mv .env.tmp .env
    else
        echo "LIBOQS_DYLIB_PATH=$SO_PATH" >> .env
    fi
fi

echo "✅ Setup Complete!"
echo "👉 Edit .env to set your 'TARGET_RECEIVER_IP' to your friend's IP."
echo "👉 Run 'python server.py' to start."

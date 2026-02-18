#!/bin/bash

# Exit on error
set -e

echo "🔧 Setting up liboqs environment..."

# Check dependencies
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v cmake &> /dev/null; then
        echo "❌ CMake not found. Please install it (e.g., brew install cmake)"
        exit 1
    fi
    if ! command -v ninja &> /dev/null; then
        echo "⚠️ Ninja not found. It speeds up builds (brew install ninja). Using Make instead."
    fi
fi

# Directory structure
BASE_DIR="$(pwd)"
LIBOQS_DIR="$BASE_DIR/liboqs"
BUILD_DIR="$LIBOQS_DIR/build"

# 1. Clone or Update liboqs
if [ -d "$LIBOQS_DIR" ]; then
    echo "🔄 liboqs directory exists. Pulling latest changes..."
    cd "$LIBOQS_DIR"
    git pull origin main
else
    echo "⬇️ Cloning liboqs (main branch)..."
    git clone https://github.com/open-quantum-safe/liboqs.git
    cd "$LIBOQS_DIR"
fi

# 2. Configure CMake
echo "⚙️ Configuring CMake..."
mkdir -p build
cd build

# Use Ninja if available, else standard Makefiles
if command -v ninja &> /dev/null; then
    cmake -GNinja -DBUILD_SHARED_LIBS=ON -DOQS_BUILD_ONLY_LIB=ON ..
else
    cmake -DBUILD_SHARED_LIBS=ON -DOQS_BUILD_ONLY_LIB=ON ..
fi

# 3. Build
echo "🏗️ Building liboqs..."
if command -v ninja &> /dev/null; then
    ninja
else
    make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu) 
fi

echo "✅ Build complete!"
echo "📍 Library location:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "   $BUILD_DIR/lib/liboqs.dylib"
else
    echo "   $BUILD_DIR/lib/liboqs.so"
fi

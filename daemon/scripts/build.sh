#!/bin/bash
# Build script for cortexd daemon
# Usage: ./scripts/build.sh [Release|Debug]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_TYPE="${1:-Release}"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "=== Building cortexd ==="
echo "Build Type: $BUILD_TYPE"
echo "Build Directory: $BUILD_DIR"
echo ""

# Check for required tools
check_tool() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: $1 not found. Install with: $2"
        exit 1
    fi
}

echo "Checking build tools..."
check_tool cmake "sudo apt install cmake"
check_tool pkg-config "sudo apt install pkg-config"
check_tool g++ "sudo apt install build-essential"

# Check for required libraries
check_lib() {
    if ! pkg-config --exists "$1" 2>/dev/null; then
        echo "Error: $1 not found. Install with: sudo apt install $2"
        exit 1
    fi
}

echo "Checking dependencies..."
check_lib libsystemd libsystemd-dev
check_lib openssl libssl-dev
check_lib sqlite3 libsqlite3-dev
check_lib uuid uuid-dev

# Check for llama.cpp (optional)
if [ -f /usr/local/lib/libllama.so ] || [ -f /usr/lib/libllama.so ]; then
    echo "✓ llama.cpp found"
    HAVE_LLAMA=1
else
    echo "⚠ llama.cpp not found (LLM features will be limited)"
    echo "  Install from: https://github.com/ggerganov/llama.cpp"
    HAVE_LLAMA=0
fi

echo ""

# Create build directory
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Run CMake
echo "Running CMake..."
cmake -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
      -DBUILD_TESTS=OFF \
      "$SCRIPT_DIR"

# Build
echo ""
echo "Building..."
make -j"$(nproc)"

# Show result
echo ""
echo "=== Build Complete ==="
echo ""
echo "Binary: $BUILD_DIR/cortexd"
ls -lh "$BUILD_DIR/cortexd"
echo ""
echo "To install: sudo ./scripts/install.sh"
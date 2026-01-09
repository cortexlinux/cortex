#!/bin/bash
# Cortex Linux - llama.cpp Build Script
#
# Builds llama.cpp Python bindings with optimal settings for the current system.
# Supports: CUDA, ROCm, Metal, Vulkan, and CPU backends.
#
# Usage:
#   ./scripts/build_llamacpp.sh              # Auto-detect and build
#   ./scripts/build_llamacpp.sh cuda         # Build with CUDA support
#   ./scripts/build_llamacpp.sh rocm         # Build with ROCm support
#   ./scripts/build_llamacpp.sh metal        # Build with Metal support (macOS)
#   ./scripts/build_llamacpp.sh cpu          # CPU only build
#
# Author: Cortex Linux Team
# License: Apache 2.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║        Cortex Linux - llama.cpp Build System              ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}▶ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Detect the best backend
detect_backend() {
    # Check for CUDA
    if command -v nvidia-smi &> /dev/null; then
        if nvidia-smi &> /dev/null; then
            echo "cuda"
            return
        fi
    fi

    # Check for ROCm
    if command -v rocm-smi &> /dev/null; then
        if rocm-smi &> /dev/null; then
            echo "rocm"
            return
        fi
    fi

    # Check for macOS Metal
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "metal"
        return
    fi

    # Check for Vulkan
    if command -v vulkaninfo &> /dev/null; then
        echo "vulkan"
        return
    fi

    # Default to CPU
    echo "cpu"
}

# Get CPU architecture
get_arch() {
    local arch=$(uname -m)
    case $arch in
        x86_64|amd64)
            echo "x86_64"
            ;;
        aarch64|arm64)
            echo "arm64"
            ;;
        *)
            echo "$arch"
            ;;
    esac
}

# Build llama-cpp-python with specified backend
build_llamacpp() {
    local backend=$1
    local arch=$(get_arch)
    
    print_step "Building llama-cpp-python for ${backend} on ${arch}"

    # Set CMAKE arguments based on backend
    local cmake_args=""

    case $backend in
        cuda)
            print_step "Configuring CUDA backend..."
            cmake_args="-DGGML_CUDA=on"
            
            # Check CUDA version and set compute capabilities
            if command -v nvcc &> /dev/null; then
                local cuda_version=$(nvcc --version | grep release | awk '{print $5}' | cut -d',' -f1)
                print_step "Detected CUDA version: ${cuda_version}"
            fi
            
            # Set compute capabilities for common GPUs
            # 6.1 = GTX 1000 series
            # 7.0 = V100
            # 7.5 = RTX 2000/3000 series
            # 8.0 = A100
            # 8.6 = RTX 3000 series
            # 8.9 = RTX 4000 series
            # 9.0 = H100
            cmake_args="${cmake_args} -DGGML_CUDA_CUDA_ARCHITECTURES=61;70;75;80;86;89"
            ;;
        rocm)
            print_step "Configuring ROCm backend..."
            cmake_args="-DGGML_HIPBLAS=on"
            
            # Set ROCm target architectures
            # gfx900 = Vega
            # gfx906 = Radeon VII
            # gfx908 = MI100
            # gfx90a = MI200
            # gfx1030 = RX 6000 series
            # gfx1100 = RX 7000 series
            cmake_args="${cmake_args} -DAMDGPU_TARGETS=gfx900;gfx906;gfx908;gfx90a;gfx1030;gfx1100"
            ;;
        metal)
            print_step "Configuring Metal backend (Apple Silicon)..."
            cmake_args="-DGGML_METAL=on"
            ;;
        vulkan)
            print_step "Configuring Vulkan backend..."
            cmake_args="-DGGML_VULKAN=on"
            ;;
        cpu)
            print_step "Configuring CPU backend..."
            cmake_args="-DGGML_BLAS=on -DGGML_BLAS_VENDOR=OpenBLAS"
            
            # Enable CPU optimizations
            if [[ "$arch" == "x86_64" ]]; then
                cmake_args="${cmake_args} -DGGML_AVX=on -DGGML_AVX2=on -DGGML_FMA=on -DGGML_F16C=on"
            elif [[ "$arch" == "arm64" ]]; then
                cmake_args="${cmake_args} -DGGML_ACCELERATE=on"
            fi
            ;;
        *)
            print_error "Unknown backend: ${backend}"
            exit 1
            ;;
    esac

    # Add common optimizations
    cmake_args="${cmake_args} -DCMAKE_BUILD_TYPE=Release"

    # Set environment and install
    print_step "Installing llama-cpp-python with CMAKE_ARGS='${cmake_args}'"
    
    # Uninstall existing version
    pip uninstall -y llama-cpp-python 2>/dev/null || true
    
    # Build and install
    CMAKE_ARGS="${cmake_args}" pip install llama-cpp-python --no-cache-dir --force-reinstall

    print_success "llama-cpp-python built successfully with ${backend} backend"
}

# Verify installation
verify_installation() {
    print_step "Verifying installation..."
    
    python3 -c "
from llama_cpp import Llama
import llama_cpp
print(f'llama-cpp-python version: {llama_cpp.__version__}')

# Check for CUDA support
try:
    import ctypes
    ctypes.CDLL('libcublas.so')
    print('✓ CUDA libraries found')
except OSError:
    print('  CUDA libraries not found (OK if using CPU/Metal)')

# Check for Metal support (macOS)
import platform
if platform.system() == 'Darwin':
    print('✓ Running on macOS - Metal support available')

print('✓ Installation verified!')
"
}

# Main script
main() {
    print_header
    
    local backend=${1:-"auto"}
    
    # Auto-detect backend if not specified
    if [[ "$backend" == "auto" ]]; then
        print_step "Auto-detecting best backend..."
        backend=$(detect_backend)
        print_success "Detected backend: ${backend}"
    fi
    
    # Check dependencies
    print_step "Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    if ! command -v pip &> /dev/null; then
        print_error "pip is required but not installed"
        exit 1
    fi
    
    if ! command -v cmake &> /dev/null; then
        print_warning "CMake not found. Installing..."
        if command -v apt &> /dev/null; then
            sudo apt update && sudo apt install -y cmake build-essential
        elif command -v brew &> /dev/null; then
            brew install cmake
        else
            print_error "Please install CMake manually"
            exit 1
        fi
    fi
    
    # Install OpenBLAS for CPU builds
    if [[ "$backend" == "cpu" ]]; then
        if command -v apt &> /dev/null; then
            print_step "Installing OpenBLAS..."
            sudo apt update && sudo apt install -y libopenblas-dev
        elif command -v brew &> /dev/null; then
            brew install openblas
        fi
    fi
    
    # Build llama-cpp-python
    build_llamacpp "$backend"
    
    # Verify installation
    verify_installation
    
    echo ""
    print_success "llama.cpp integration complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Download a model:    cortex model download recommended"
    echo "  2. Set provider:        export CORTEX_PROVIDER=llamacpp"
    echo "  3. Test inference:      cortex install nginx --dry-run"
    echo ""
}

# Handle help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "Usage: $0 [backend]"
    echo ""
    echo "Backends:"
    echo "  auto    - Auto-detect best backend (default)"
    echo "  cuda    - NVIDIA CUDA support"
    echo "  rocm    - AMD ROCm support"
    echo "  metal   - Apple Metal support (macOS)"
    echo "  vulkan  - Vulkan support"
    echo "  cpu     - CPU only with OpenBLAS"
    echo ""
    exit 0
fi

main "$@"


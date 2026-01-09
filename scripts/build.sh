#!/bin/bash
# Cortex Linux Master Build Script
# One-command ISO build with all dependencies
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

# Configuration
VERSION="${CORTEX_VERSION:-0.1.0}"
ARCH="${CORTEX_ARCH:-amd64}"
BUILD_TYPE="${1:-offline}"  # netinst or offline

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $*"; }
error() { echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $*" >&2; }
header() { echo -e "\n${BLUE}========================================${NC}\n${BLUE}$*${NC}\n${BLUE}========================================${NC}\n"; }

usage() {
    cat << EOF
Cortex Linux Build Script

Usage: $(basename "$0") [build-type] [options]

Build Types:
    netinst     Build minimal network installer ISO (~500MB)
    offline     Build full offline ISO with package pool (~2-4GB)
    packages    Build Debian packages only
    all         Build both ISOs

Options:
    -v, --version   Set version (default: 0.1.0)
    -a, --arch      Set architecture (default: amd64)
    -c, --clean     Clean before building
    -h, --help      Show this help

Examples:
    $(basename "$0") offline
    $(basename "$0") netinst --clean
    $(basename "$0") all --version 0.2.0

Requirements:
    - Debian 12+ or Ubuntu 24.04+ build host
    - Root/sudo access for live-build
    - ~10GB free disk space
    - Internet connection (for package downloads)
EOF
}

check_requirements() {
    header "Checking Requirements"
    
    local missing=0
    
    # Check OS
    if [ -f /etc/debian_version ]; then
        log "Debian-based OS detected"
    else
        warn "Non-Debian OS - build may not work correctly"
    fi
    
    # Check for required commands
    local required_cmds=(
        "dpkg-buildpackage"
        "lb"
        "debootstrap"
        "xorriso"
        "mksquashfs"
    )
    
    for cmd in "${required_cmds[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            log "Found: $cmd"
        else
            error "Missing: $cmd"
            ((missing++))
        fi
    done
    
    if [ $missing -gt 0 ]; then
        error ""
        error "$missing required tools missing. Install with:"
        error "  sudo apt-get install live-build debootstrap squashfs-tools xorriso dpkg-dev devscripts"
        exit 1
    fi
    
    # Check disk space
    local free_space
    free_space=$(df -BG "${PROJECT_ROOT}" | tail -1 | awk '{print $4}' | tr -d 'G')
    if [ "$free_space" -lt 10 ]; then
        warn "Low disk space: ${free_space}GB free (recommend 10GB+)"
    else
        log "Disk space OK: ${free_space}GB free"
    fi
    
    log "All requirements satisfied"
}

install_dependencies() {
    header "Installing Build Dependencies"
    
    sudo apt-get update
    sudo apt-get install -y \
        live-build \
        debootstrap \
        squashfs-tools \
        xorriso \
        isolinux \
        syslinux-efi \
        grub-pc-bin \
        grub-efi-amd64-bin \
        mtools \
        dosfstools \
        dpkg-dev \
        devscripts \
        debhelper \
        fakeroot \
        gnupg
    
    log "Dependencies installed"
}

build_packages() {
    header "Building Debian Packages"
    
    cd "${PROJECT_ROOT}"
    
    # Build each package
    for pkg in cortex-archive-keyring cortex-core cortex-full; do
        log "Building ${pkg}..."
        cd "${PROJECT_ROOT}/packages/${pkg}"
        
        # Clean previous builds
        rm -f ../cortex-*.deb ../cortex-*.buildinfo ../cortex-*.changes 2>/dev/null || true
        
        # Build
        dpkg-buildpackage -us -uc -b
        
        log "${pkg} built successfully"
    done
    
    # Move packages to output
    mkdir -p "${PROJECT_ROOT}/output/packages"
    mv "${PROJECT_ROOT}/packages"/*.deb "${PROJECT_ROOT}/output/packages/" 2>/dev/null || true
    
    log "All packages built: ${PROJECT_ROOT}/output/packages/"
}

configure_live_build() {
    header "Configuring Live-Build"
    
    cd "${PROJECT_ROOT}/iso/live-build"
    
    # Make auto scripts executable
    chmod +x auto/* 2>/dev/null || true
    
    # Clean previous configuration
    sudo lb clean --purge 2>/dev/null || true
    
    # Run configuration
    sudo lb config
    
    # Copy built packages to chroot
    if [ -d "${PROJECT_ROOT}/output/packages" ]; then
        mkdir -p config/packages.chroot/
        cp "${PROJECT_ROOT}/output/packages"/*.deb config/packages.chroot/
        log "Packages copied to chroot"
    fi
    
    log "Live-build configured"
}

build_iso() {
    local iso_type="$1"
    
    header "Building ISO: ${iso_type}"
    
    cd "${PROJECT_ROOT}/iso/live-build"
    
    # Build
    log "Starting build (this may take 30-60 minutes)..."
    sudo lb build 2>&1 | tee "${PROJECT_ROOT}/build-${iso_type}.log"
    
    # Move output
    mkdir -p "${PROJECT_ROOT}/output"
    
    local iso_file
    iso_file=$(find . -maxdepth 1 -name "*.iso" -type f | head -1)
    
    if [ -n "$iso_file" ] && [ -f "$iso_file" ]; then
        local output_name="cortex-linux-${VERSION}-${ARCH}-${iso_type}.iso"
        mv "$iso_file" "${PROJECT_ROOT}/output/${output_name}"
        
        # Generate checksums
        cd "${PROJECT_ROOT}/output"
        sha256sum "${output_name}" > "${output_name}.sha256"
        sha512sum "${output_name}" > "${output_name}.sha512"
        
        log "ISO built: ${PROJECT_ROOT}/output/${output_name}"
        log "Checksums generated"
    else
        error "ISO build failed - no ISO file found"
        error "Check build log: ${PROJECT_ROOT}/build-${iso_type}.log"
        exit 1
    fi
}

clean_build() {
    header "Cleaning Build Environment"
    
    cd "${PROJECT_ROOT}/iso/live-build"
    sudo lb clean --purge 2>/dev/null || true
    
    rm -rf "${PROJECT_ROOT}/output" 2>/dev/null || true
    rm -f "${PROJECT_ROOT}"/*.log 2>/dev/null || true
    
    log "Build environment cleaned"
}

generate_sbom() {
    header "Generating SBOM"
    
    chmod +x "${PROJECT_ROOT}/sbom/generate-sbom.sh"
    "${PROJECT_ROOT}/sbom/generate-sbom.sh" "${PROJECT_ROOT}/output/sbom"
}

run_tests() {
    header "Running Verification Tests"
    
    chmod +x "${PROJECT_ROOT}/tests"/*.sh
    
    "${PROJECT_ROOT}/tests/verify-packages.sh" || warn "Package tests had issues"
    "${PROJECT_ROOT}/tests/verify-preseed.sh" || warn "Preseed tests had issues"
    
    # ISO tests if ISO exists
    local iso_file
    iso_file=$(find "${PROJECT_ROOT}/output" -name "*.iso" -type f | head -1)
    if [ -n "$iso_file" ]; then
        "${PROJECT_ROOT}/tests/verify-iso.sh" "$iso_file" || warn "ISO tests had issues"
    fi
}

# Parse arguments
CLEAN=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -a|--arch)
            ARCH="$2"
            shift 2
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        netinst|offline|packages|all)
            BUILD_TYPE="$1"
            shift
            ;;
        *)
            error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
header "Cortex Linux Build System"
log "Version: ${VERSION}"
log "Architecture: ${ARCH}"
log "Build Type: ${BUILD_TYPE}"

# Clean if requested
if [ "$CLEAN" = true ]; then
    clean_build
fi

# Check requirements
check_requirements

# Build based on type
case "$BUILD_TYPE" in
    packages)
        build_packages
        ;;
    netinst)
        build_packages
        configure_live_build
        build_iso "netinst"
        generate_sbom
        run_tests
        ;;
    offline)
        build_packages
        configure_live_build
        build_iso "offline"
        generate_sbom
        run_tests
        ;;
    all)
        build_packages
        configure_live_build
        build_iso "netinst"
        clean_build
        configure_live_build
        build_iso "offline"
        generate_sbom
        run_tests
        ;;
    *)
        error "Unknown build type: ${BUILD_TYPE}"
        usage
        exit 1
        ;;
esac

header "Build Complete"
log "Output: ${PROJECT_ROOT}/output/"
ls -la "${PROJECT_ROOT}/output/" 2>/dev/null || true

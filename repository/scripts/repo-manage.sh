#!/bin/bash
# Cortex Linux APT Repository Management
# Manages package publishing, signing, and snapshots
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/.."
REPO_DIR="${REPO_ROOT}/repo"
KEYS_DIR="${REPO_ROOT}/keys"
POOL_DIR="${REPO_DIR}/pool"
DISTS_DIR="${REPO_DIR}/dists"

# Configuration
GPG_KEY_ID="${CORTEX_GPG_KEY_ID:-}"
REPO_ORIGIN="Cortex"
REPO_LABEL="Cortex"
REPO_CODENAME="cortex"
REPO_ARCHITECTURES="amd64 arm64"
REPO_COMPONENTS="main"
REPO_DESCRIPTION="Cortex Linux Package Repository"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
    cat << EOF
Cortex Linux Repository Management

Usage: $(basename "$0") <command> [options]

Commands:
    init            Initialize repository structure
    add <pkg.deb>   Add package to repository
    remove <pkg>    Remove package from repository
    publish         Generate and sign repository metadata
    snapshot        Create dated snapshot of repository
    verify          Verify repository integrity
    export          Export repository for offline use

Options:
    -k, --key-id    GPG key ID for signing
    -d, --dir       Repository directory (default: ./repo)
    -h, --help      Show this help message

Environment:
    CORTEX_GPG_KEY_ID    GPG key ID for signing

Examples:
    $(basename "$0") init
    $(basename "$0") add packages/cortex-core_0.1.0-1_all.deb
    $(basename "$0") publish
    $(basename "$0") snapshot
EOF
}

cmd_init() {
    log "Initializing Cortex repository structure..."
    
    # Create directory structure
    mkdir -p "${POOL_DIR}/main"
    mkdir -p "${DISTS_DIR}/${REPO_CODENAME}/main/binary-amd64"
    mkdir -p "${DISTS_DIR}/${REPO_CODENAME}/main/binary-arm64"
    mkdir -p "${DISTS_DIR}/${REPO_CODENAME}-updates/main/binary-amd64"
    mkdir -p "${DISTS_DIR}/${REPO_CODENAME}-updates/main/binary-arm64"
    mkdir -p "${DISTS_DIR}/${REPO_CODENAME}-security/main/binary-amd64"
    mkdir -p "${DISTS_DIR}/${REPO_CODENAME}-security/main/binary-arm64"
    mkdir -p "${KEYS_DIR}"
    
    # Create .gitkeep files
    touch "${POOL_DIR}/main/.gitkeep"
    touch "${KEYS_DIR}/.gitkeep"
    
    log "Repository structure initialized at ${REPO_DIR}"
}

cmd_add() {
    local deb_file="$1"
    
    if [ -z "$deb_file" ] || [ ! -f "$deb_file" ]; then
        error "Package file not found: $deb_file"
        exit 1
    fi
    
    log "Adding package: $deb_file"
    
    # Extract package info
    local pkg_name
    pkg_name=$(dpkg-deb --field "$deb_file" Package)
    local pkg_version
    pkg_version=$(dpkg-deb --field "$deb_file" Version)
    local pkg_arch
    pkg_arch=$(dpkg-deb --field "$deb_file" Architecture)
    
    # Determine pool path (first letter or lib prefix)
    local pool_prefix
    if [[ "$pkg_name" == lib* ]]; then
        pool_prefix="${pkg_name:0:4}"
    else
        pool_prefix="${pkg_name:0:1}"
    fi
    
    local pool_path="${POOL_DIR}/main/${pool_prefix}/${pkg_name}"
    mkdir -p "$pool_path"
    
    # Copy package
    cp "$deb_file" "$pool_path/"
    
    log "Added: ${pkg_name}_${pkg_version}_${pkg_arch}.deb"
}

cmd_publish() {
    log "Publishing repository metadata..."
    
    if [ -z "$GPG_KEY_ID" ]; then
        warn "No GPG key ID set. Repository will not be signed."
        warn "Set CORTEX_GPG_KEY_ID or use --key-id"
    fi
    
    for suite in "${REPO_CODENAME}" "${REPO_CODENAME}-updates" "${REPO_CODENAME}-security"; do
        local suite_dir="${DISTS_DIR}/${suite}"
        
        for arch in amd64 arm64; do
            local arch_dir="${suite_dir}/main/binary-${arch}"
            mkdir -p "$arch_dir"
            
            # Generate Packages file
            log "Generating Packages for ${suite}/${arch}..."
            (cd "${REPO_DIR}" && dpkg-scanpackages --arch "$arch" pool/main > "${arch_dir}/Packages" 2>/dev/null || true)
            gzip -9 -k -f "${arch_dir}/Packages"
            xz -9 -k -f "${arch_dir}/Packages"
            
            # Generate Release file for component
            cat > "${arch_dir}/Release" << EOF
Archive: ${suite}
Component: main
Origin: ${REPO_ORIGIN}
Label: ${REPO_LABEL}
Architecture: ${arch}
EOF
        done
        
        # Generate suite Release file
        log "Generating Release for ${suite}..."
        generate_release "$suite_dir" "$suite"
        
        # Sign if key available
        if [ -n "$GPG_KEY_ID" ]; then
            log "Signing Release for ${suite}..."
            gpg --default-key "$GPG_KEY_ID" --armor --detach-sign -o "${suite_dir}/Release.gpg" "${suite_dir}/Release"
            gpg --default-key "$GPG_KEY_ID" --armor --clearsign -o "${suite_dir}/InRelease" "${suite_dir}/Release"
        fi
    done
    
    log "Repository published successfully"
}

generate_release() {
    local suite_dir="$1"
    local suite="$2"
    local date
    date=$(date -R)
    local valid_until
    valid_until=$(date -R -d "+14 days")
    
    cat > "${suite_dir}/Release" << EOF
Origin: ${REPO_ORIGIN}
Label: ${REPO_LABEL}
Suite: ${suite}
Codename: ${suite}
Architectures: ${REPO_ARCHITECTURES}
Components: ${REPO_COMPONENTS}
Description: ${REPO_DESCRIPTION}
Date: ${date}
Valid-Until: ${valid_until}
Acquire-By-Hash: yes
EOF
    
    # Add checksums
    echo "MD5Sum:" >> "${suite_dir}/Release"
    (cd "$suite_dir" && find . -type f \( -name "Packages*" -o -name "Release" \) -exec md5sum {} \; | \
        sed 's|\./||' | awk '{printf " %s %8d %s\n", $1, 0, $2}') >> "${suite_dir}/Release"
    
    echo "SHA256:" >> "${suite_dir}/Release"
    (cd "$suite_dir" && find . -type f \( -name "Packages*" -o -name "Release" \) -exec sha256sum {} \; | \
        sed 's|\./||' | awk '{printf " %s %8d %s\n", $1, 0, $2}') >> "${suite_dir}/Release"
}

cmd_snapshot() {
    local snapshot_date
    snapshot_date=$(date +%Y%m%d)
    local snapshot_dir="${REPO_DIR}/snapshots/${snapshot_date}"
    
    log "Creating snapshot: ${snapshot_date}"
    
    mkdir -p "$snapshot_dir"
    
    # Copy current repo state
    cp -r "${DISTS_DIR}" "${snapshot_dir}/"
    cp -r "${POOL_DIR}" "${snapshot_dir}/"
    
    log "Snapshot created at ${snapshot_dir}"
}

cmd_verify() {
    log "Verifying repository integrity..."
    
    local errors=0
    
    # Check directory structure
    for dir in "$POOL_DIR" "$DISTS_DIR"; do
        if [ ! -d "$dir" ]; then
            error "Missing directory: $dir"
            ((errors++))
        fi
    done
    
    # Check Release files
    for suite in "${REPO_CODENAME}" "${REPO_CODENAME}-updates" "${REPO_CODENAME}-security"; do
        local release_file="${DISTS_DIR}/${suite}/Release"
        if [ ! -f "$release_file" ]; then
            warn "Missing Release file: $release_file"
        fi
    done
    
    # Verify GPG signatures
    if [ -n "$GPG_KEY_ID" ]; then
        for suite in "${REPO_CODENAME}" "${REPO_CODENAME}-updates" "${REPO_CODENAME}-security"; do
            local inrelease="${DISTS_DIR}/${suite}/InRelease"
            if [ -f "$inrelease" ]; then
                if gpg --verify "$inrelease" 2>/dev/null; then
                    log "Signature valid: $inrelease"
                else
                    error "Invalid signature: $inrelease"
                    ((errors++))
                fi
            fi
        done
    fi
    
    if [ $errors -eq 0 ]; then
        log "Repository verification passed"
    else
        error "Repository verification failed with $errors errors"
        exit 1
    fi
}

cmd_export() {
    local export_dir="${1:-cortex-repo-export}"
    
    log "Exporting repository for offline use..."
    
    mkdir -p "$export_dir"
    
    # Copy repository
    cp -r "${DISTS_DIR}" "${export_dir}/"
    cp -r "${POOL_DIR}" "${export_dir}/"
    
    # Create README
    cat > "${export_dir}/README.md" << 'EOF'
# Cortex Linux Offline Repository

This is an offline export of the Cortex Linux APT repository.

## Usage

1. Mount or copy this directory to the target system
2. Add to APT sources:

```
# /etc/apt/sources.list.d/cortex-offline.sources
Types: deb
URIs: file:/path/to/this/directory
Suites: cortex
Components: main
Signed-By: /usr/share/keyrings/cortex-archive-keyring.gpg
```

3. Update package lists:
```
sudo apt update
```

## Verification

Verify the repository signature:
```
gpg --verify dists/cortex/InRelease
```
EOF
    
    # Create tarball
    tar -czf "${export_dir}.tar.gz" "$export_dir"
    
    log "Repository exported to ${export_dir}.tar.gz"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -k|--key-id)
            GPG_KEY_ID="$2"
            shift 2
            ;;
        -d|--dir)
            REPO_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        init|add|remove|publish|snapshot|verify|export)
            COMMAND="$1"
            shift
            break
            ;;
        *)
            error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Execute command
case "${COMMAND:-}" in
    init)
        cmd_init
        ;;
    add)
        cmd_add "$@"
        ;;
    publish)
        cmd_publish
        ;;
    snapshot)
        cmd_snapshot
        ;;
    verify)
        cmd_verify
        ;;
    export)
        cmd_export "$@"
        ;;
    *)
        usage
        exit 1
        ;;
esac

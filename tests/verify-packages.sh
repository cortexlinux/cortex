#!/bin/bash
# Cortex Linux Package Verification Tests
# Validates Debian package structure and dependencies
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGES_DIR="${SCRIPT_DIR}/../packages"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

pass() { echo -e "${GREEN}[PASS]${NC} $*"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; ((FAIL++)); }
info() { echo -e "[INFO] $*"; }

info "================================================"
info "Cortex Linux Package Verification"
info "================================================"

# Test debian/control files
test_control_files() {
    info "Testing debian/control files..."
    
    for pkg_dir in "${PACKAGES_DIR}"/*/; do
        local pkg_name
        pkg_name=$(basename "$pkg_dir")
        local control_file="${pkg_dir}debian/control"
        
        if [ -f "$control_file" ]; then
            # Check required fields
            local required_fields=("Source:" "Package:" "Architecture:" "Description:")
            local missing=0
            
            for field in "${required_fields[@]}"; do
                if ! grep -q "^${field}" "$control_file"; then
                    info "  ${pkg_name}: Missing field ${field}"
                    ((missing++))
                fi
            done
            
            if [ $missing -eq 0 ]; then
                pass "${pkg_name}: debian/control valid"
            else
                fail "${pkg_name}: debian/control missing $missing required fields"
            fi
        else
            fail "${pkg_name}: debian/control not found"
        fi
    done
}

# Test debian/changelog
test_changelog_files() {
    info "Testing debian/changelog files..."
    
    for pkg_dir in "${PACKAGES_DIR}"/*/; do
        local pkg_name
        pkg_name=$(basename "$pkg_dir")
        local changelog_file="${pkg_dir}debian/changelog"
        
        if [ -f "$changelog_file" ]; then
            # Check format
            if head -1 "$changelog_file" | grep -qE "^[a-z0-9-]+ \([^)]+\)"; then
                pass "${pkg_name}: debian/changelog valid format"
            else
                fail "${pkg_name}: debian/changelog invalid format"
            fi
        else
            fail "${pkg_name}: debian/changelog not found"
        fi
    done
}

# Test debian/rules
test_rules_files() {
    info "Testing debian/rules files..."
    
    for pkg_dir in "${PACKAGES_DIR}"/*/; do
        local pkg_name
        pkg_name=$(basename "$pkg_dir")
        local rules_file="${pkg_dir}debian/rules"
        
        if [ -f "$rules_file" ]; then
            # Check it's executable or has shebang
            if [ -x "$rules_file" ] || head -1 "$rules_file" | grep -q "^#!/"; then
                pass "${pkg_name}: debian/rules valid"
            else
                fail "${pkg_name}: debian/rules not executable"
            fi
        else
            fail "${pkg_name}: debian/rules not found"
        fi
    done
}

# Test for lintian issues (if lintian installed)
test_lintian() {
    if ! command -v lintian &>/dev/null; then
        info "Skipping lintian checks (lintian not installed)"
        return
    fi
    
    info "Running lintian checks..."
    
    # Find built packages
    local debs
    debs=$(find "${PACKAGES_DIR}" -name "*.deb" 2>/dev/null)
    
    if [ -z "$debs" ]; then
        info "No .deb files found - build packages first"
        return
    fi
    
    for deb in $debs; do
        local pkg_name
        pkg_name=$(basename "$deb")
        
        # Run lintian with pedantic checks
        local lintian_output
        if lintian_output=$(lintian --fail-on error "$deb" 2>&1); then
            pass "${pkg_name}: lintian passed"
        else
            fail "${pkg_name}: lintian found issues"
            echo "$lintian_output" | head -20
        fi
    done
}

# Run tests
test_control_files
test_changelog_files
test_rules_files
test_lintian

# Summary
info ""
info "================================================"
info "Package Verification Summary"
info "================================================"
info "Passed: $PASS"
info "Failed: $FAIL"

if [ $FAIL -gt 0 ]; then
    exit 1
else
    exit 0
fi

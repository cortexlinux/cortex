#!/bin/bash
# Cortex Linux Preseed Verification Tests
# Validates preseed files for automated installation
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESEED_DIR="${SCRIPT_DIR}/../iso/preseed"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "${GREEN}[PASS]${NC} $*"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; ((FAIL++)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; ((WARN++)); }
info() { echo -e "[INFO] $*"; }

info "================================================"
info "Cortex Linux Preseed Verification"
info "================================================"

# Find preseed files
PRESEED_FILES=$(find "${PRESEED_DIR}" -name "*.preseed" -o -name "*.cfg" 2>/dev/null)

if [ -z "$PRESEED_FILES" ]; then
    fail "No preseed files found in ${PRESEED_DIR}"
    exit 1
fi

for preseed_file in $PRESEED_FILES; do
    info ""
    info "Checking: $(basename "$preseed_file")"
    
    # Test 1: File is readable
    if [ -r "$preseed_file" ]; then
        pass "File is readable"
    else
        fail "File is not readable"
        continue
    fi
    
    # Test 2: Check for basic preseed structure
    if grep -qE "^d-i " "$preseed_file"; then
        pass "Contains d-i directives"
    else
        fail "No d-i directives found"
    fi
    
    # Test 3: Check for critical settings
    local critical_settings=(
        "debian-installer/locale"
        "keyboard-configuration"
        "netcfg/"
        "partman"
        "passwd/"
        "grub-installer"
    )
    
    local missing=0
    for setting in "${critical_settings[@]}"; do
        if ! grep -q "$setting" "$preseed_file"; then
            warn "Missing critical setting: $setting"
            ((missing++))
        fi
    done
    
    if [ $missing -eq 0 ]; then
        pass "All critical settings present"
    fi
    
    # Test 4: Check for syntax issues (basic)
    # Each d-i line should have at least 3 fields
    local syntax_errors=0
    while IFS= read -r line; do
        if [[ "$line" =~ ^d-i ]]; then
            local field_count
            field_count=$(echo "$line" | awk '{print NF}')
            if [ "$field_count" -lt 3 ]; then
                warn "Possible syntax error: $line"
                ((syntax_errors++))
            fi
        fi
    done < "$preseed_file"
    
    if [ $syntax_errors -eq 0 ]; then
        pass "No obvious syntax errors"
    fi
    
    # Test 5: Check for hardcoded passwords (security)
    if grep -qE "passwd/root-password\s+string\s+[^$]" "$preseed_file"; then
        fail "Contains plaintext root password"
    elif grep -qE "passwd/user-password\s+string\s+[^$]" "$preseed_file"; then
        fail "Contains plaintext user password"
    else
        pass "No plaintext passwords found"
    fi
    
    # Test 6: Check for proper hashed passwords
    if grep -qE "passwd/.*-password-crypted" "$preseed_file"; then
        pass "Uses crypted passwords"
    else
        warn "No crypted passwords - may require manual input"
    fi
    
    # Test 7: Check late_command safety
    if grep -q "preseed/late_command" "$preseed_file"; then
        # Check for dangerous commands
        if grep "preseed/late_command" "$preseed_file" | grep -qE "rm -rf /|chmod 777|curl.*\|.*sh"; then
            warn "late_command contains potentially dangerous operations"
        else
            pass "late_command appears safe"
        fi
    fi
done

# Summary
info ""
info "================================================"
info "Preseed Verification Summary"
info "================================================"
info "Passed: $PASS"
info "Failed: $FAIL"
info "Warnings: $WARN"

if [ $FAIL -gt 0 ]; then
    exit 1
else
    exit 0
fi

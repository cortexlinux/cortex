#!/bin/bash
# Installation script for Linux Permission Auditor


set -e  # Exit on error
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════╗"
echo "║    Linux Permission Auditor Installer        ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python3 is required but not installed${NC}"
    echo "Install Python3 with: sudo apt install python3"
    exit 1
fi

# Install auditor
echo -e "${BLUE}[*] Installing Permission Auditor...${NC}"

# Copy to /usr/local/bin
sudo cp ../src/auditor.py /usr/local/bin/perm-audit
sudo chmod +x /usr/local/bin/perm-audit

echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo -e "You can now use:"
echo -e "  ${BLUE}perm-audit /path/to/scan${NC}"
echo ""
echo -e "Examples:"
echo -e "  perm-audit /var/www"
echo -e "  perm-audit /home -r --fix"
echo -e "  perm-audit --help"
echo ""
echo -e "${YELLOW}Note: This tool only identifies issues.${NC}"
echo -e "${YELLOW}It does NOT automatically fix anything.${NC}"

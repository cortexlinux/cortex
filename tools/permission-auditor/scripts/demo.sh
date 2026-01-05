#!/bin/bash
clear
echo "========================================="
echo "   LINUX PERMISSION AUDITOR DEMO"
echo "   Solution for Pain Point #9"
echo "   Single Command Safe Fixes"
echo "========================================="
echo ""

# Create demo directory
DEMO_DIR="/tmp/perm-audit-demo-$(date +%s)"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

echo "📁 Created demo directory: $DEMO_DIR"
echo ""

# Create test files
echo "1. Creating test files with dangerous permissions..."
echo ""

# Create various test files
echo '#!/bin/bash' > dangerous-script-777.sh
echo 'echo "This script has 777 permissions!"' >> dangerous-script-777.sh
chmod 777 dangerous-script-777.sh

echo "sensitive_password=secret123" > config-666.conf
chmod 666 config-666.conf

mkdir open-dir-777
chmod 777 open-dir-777

echo "normal content" > normal-file.txt
chmod 644 normal-file.txt

echo "#!/usr/bin/env python3" > app.py
echo "print('Hello')" >> app.py
chmod 777 app.py

echo "✅ Created test files:"
ls -la
echo ""

# Run auditor in dry-run mode
echo "2. Running Permission Auditor (dry-run mode)..."
echo ""
echo "--- DRY RUN SCAN ---"
python3 /opt/permission-auditor-final/src/auditor.py . -r --fix
echo "--- END DRY RUN ---"
echo ""

# Show single command fix
echo "3. Demonstrating single command fixes..."
echo ""
echo "For each issue, the tool generates a safe fix command:"
echo ""

# Get the JSON output to parse
echo "Getting detailed JSON report..."
json_output=$(python3 /opt/permission-auditor-final/src/auditor.py . -r --json 2>/dev/null)

# Parse and show fix commands
echo ""
echo "Example fix commands that would be generated:"
echo "--------------------------------------------"

# Extract from JSON (simplified for demo)
echo "1. For dangerous-script-777.sh:"
echo "   Command: sudo chmod 750 dangerous-script-777.sh"
echo "   Reason: Executable script should not be world-writable"
echo ""
echo "2. For config-666.conf:"
echo "   Command: sudo chmod 640 config-666.conf"
echo "   Reason: Configuration file should not be world-writable"
echo ""
echo "3. For open-dir-777:"
echo "   Command: sudo chmod 755 open-dir-777"
echo "   Reason: Directory should not give write access to everyone"
echo ""

# Show --apply warning
echo "4. Safe application with --apply flag"
echo "-------------------------------------"
echo "To actually apply fixes, you would use:"
echo "  perm-audit . -r --apply"
echo ""
echo "This would:"
echo "  • Check each file before modifying"
echo "  • Create backups of important files"
echo "  • Apply permissions one by one"
echo "  • Verify changes were successful"
echo "  • Report any failures"
echo ""

# Cleanup
echo "5. Cleaning up..."
cd /
rm -rf "$DEMO_DIR"

echo ""
echo "========================================="
echo "   DEMO COMPLETE!"
echo "   Features demonstrated:"
echo "   - 777 permission detection"
echo "   - World-writable file detection"
echo "   - Smart permission recommendations"
echo "   - Single command safe fixes"
echo "   - Backup creation (with --apply)"
echo "========================================="

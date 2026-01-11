#!/bin/bash
# Uninstall script for cortexd daemon

set -e

echo "=== Uninstalling cortexd ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Uninstallation requires root privileges"
    echo "Please run: sudo ./scripts/uninstall.sh"
    exit 1
fi

# Stop service
if systemctl is-active --quiet cortexd 2>/dev/null; then
    echo "Stopping cortexd service..."
    systemctl stop cortexd
fi

# Disable service
if systemctl is-enabled --quiet cortexd 2>/dev/null; then
    echo "Disabling cortexd service..."
    systemctl disable cortexd
fi

# Remove systemd files
echo "Removing systemd files..."
rm -f /etc/systemd/system/cortexd.service
rm -f /etc/systemd/system/cortexd.socket
systemctl daemon-reload

# Remove binary
echo "Removing binary..."
rm -f /usr/local/bin/cortexd

# Ask about config
read -p "Remove configuration (/etc/cortex)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf /etc/cortex
    echo "Configuration removed"
fi

# Ask about data
read -p "Remove data (/var/lib/cortex, /root/.cortex)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf /var/lib/cortex
    rm -rf /root/.cortex
    echo "Data removed"
fi

# Remove runtime directory
rm -rf /run/cortex

echo ""
echo "=== Uninstallation Complete ==="


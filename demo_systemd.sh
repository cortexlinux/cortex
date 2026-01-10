#!/bin/bash
# Demo script for cortex systemd helper
# Run with: asciinema rec demo.cast && bash demo_systemd.sh

echo "=== Cortex Systemd Helper Demo ==="
echo ""
sleep 1

echo "1. Check service status with plain-English explanation:"
echo "   $ cortex systemd status ssh"
sleep 1
cortex systemd status ssh
sleep 2

echo ""
echo "2. View service dependencies as a visual tree:"
echo "   $ cortex systemd deps ssh"
sleep 1
cortex systemd deps ssh
sleep 2

echo ""
echo "3. Diagnose a failed service (showing what it would look like):"
echo "   $ cortex systemd diagnose some-failed-service"
sleep 1
cortex systemd diagnose ssh 2>/dev/null || echo "[Would show diagnosis for failed services]"
sleep 2

echo ""
echo "4. Generate a systemd unit file interactively:"
echo "   $ cortex systemd generate"
echo "   [Interactive wizard would start here]"
sleep 2

echo ""
echo "=== Demo Complete ==="

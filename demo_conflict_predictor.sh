echo "Test 1: NumPy/TensorFlow conflict"
pip3 install numpy==2.1.0
cortex install "tensorflow==2.15.0" --dry-run
echo ""
clear
echo "Test 2: Flask/Werkzeug transitive dependency conflict"
pip3 install flask==2.0.0
cortex install "werkzeug==3.0.0" --dry-run
echo ""
clear
echo "Test 3: Pandas/NumPy version conflict"
pip3 install pandas==2.0.0
cortex install "numpy==1.20.0" --dry-run
echo ""
clear
echo "Test 4: Compatible packages (should work fine)"
cortex install "requests==2.31.0" --dry-run
echo ""
clear
echo "Test 5: Dry run mode"
cortex install "tensorflow==2.12.0" --dry-run
echo ""
clear
echo "Waiting 5 seconds before cleanup..."
sleep 5
clear
echo ""
echo "Cleaning up installed packages..."
pip3 uninstall -y numpy tensorflow flask werkzeug pandas requests 2>/dev/null || true
echo "Cleanup complete"

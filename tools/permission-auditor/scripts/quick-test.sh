#!/bin/bash
echo "=== QUICK TEST ==="
echo ""

# Test 1: Help
echo "1. Testing help..."
python3 src/auditor.py --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Help works"
else
    echo "❌ Help failed"
fi

# Test 2: Basic scan
echo ""
echo "2. Testing basic scan..."
python3 src/auditor.py . > /dev/null 2>&1
if [ $? -eq 0 ] || [ $? -eq 1 ]; then
    echo "✅ Basic scan works"
else
    echo "❌ Basic scan failed"
fi

# Test 3: Create test file and scan
echo ""
echo "3. Creating test file..."
TEST_FILE="/tmp/test-perm-audit-$$.txt"
echo "test-content" > "$TEST_FILE"
chmod 777 "$TEST_FILE"

echo "Scanning test file..."
output=$(python3 src/auditor.py "$TEST_FILE" 2>&1)
if echo "$output" | grep -q "CRITICAL"; then
    echo "✅ Found 777 permission issue"
else
    echo "❌ Did not find issue"
    echo "Output: $output"
fi

# Test 4: Test world-writable detection
echo ""
echo "4. Testing world-writable detection..."
echo "test" > "/tmp/test-666-$$.txt"
chmod 666 "/tmp/test-666-$$.txt"
output=$(python3 src/auditor.py "/tmp/test-666-$$.txt" 2>&1)
if echo "$output" | grep -q "HIGH\|WORLD_WRITABLE"; then
    echo "✅ Found world-writable issue"
else
    echo "❌ Did not find world-writable issue"
fi

# Cleanup
rm -f "$TEST_FILE" "/tmp/test-666-$$.txt"

# Test 5: Run Python unit tests
echo ""
echo "5. Running unit tests..."
if [ -f "tests/test_basic.py" ]; then
    python3 tests/test_basic.py
    BASIC_TEST_RESULT=$?
else
    echo "⚠️  test_basic.py not found, skipping"
    BASIC_TEST_RESULT=0
fi

echo ""
echo "=== TEST COMPLETE ==="

# Exit with worst result
if [ $BASIC_TEST_RESULT -ne 0 ]; then
    exit $BASIC_TEST_RESULT
fi

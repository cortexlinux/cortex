#!/bin/bash

echo "=== Testing Permission Auditor Docker Implementation ==="

# 1. Build the image
echo "1. Building Docker image..."
docker build -t permission-auditor:test .

# 2. Test basic scanning (dry-run)
echo -e "\n2. Testing basic scanning (dry-run)..."
docker run --rm permission-auditor:test

# 3. Test with UID/GID mapping
echo -e "\n3. Testing UID/GID mapping feature..."
docker run --rm \
  -e HOST_UID=$(id -u) \
  -e HOST_GID=$(id -g) \
  -v /tmp:/host-tmp \
  permission-auditor:test /app -r -d

# 4. Test interactive fixing
echo -e "\n4. Testing interactive mode..."
echo "n" | docker run -i --rm permission-auditor:test /app -r -i

# 5. Test JSON output
echo -e "\n5. Testing JSON output..."
docker run --rm permission-auditor:test /app -r -d --format json | head -5

# 6. Test actual fixing (with backup)
echo -e "\n6. Creating test container for safe fixing..."
TEST_CONTAINER=$(docker run -d permission-auditor:test sleep 60)
docker exec $TEST_CONTAINER python3 -m src.auditor /app/logs/app.log -f --backup
docker exec $TEST_CONTAINER ls -la /app/logs/
docker stop $TEST_CONTAINER

echo -e "\n=== Docker tests completed ==="

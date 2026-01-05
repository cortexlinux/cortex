# Advanced Dockerfile with proper UID/GID handling
# Demonstrates security best practices for Permission Auditor

FROM python:3.10-slim AS builder

WORKDIR /build

# Copy all source files
COPY src/ ./src/
COPY requirements.txt .
COPY setup.py .

# Install in development mode
RUN pip install --user -e .

# Final image
FROM python:3.10-slim

# Install only necessary system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with specific UID/GID
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g ${GROUP_ID} appgroup && \
    useradd -u ${USER_ID} -g ${GROUP_ID} -m -s /bin/bash appuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Copy source code for inspection
COPY src/ /app/src/
WORKDIR /app

# Create test directory structure with various permissions
RUN mkdir -p /app && \
    mkdir -p /app/data && \
    mkdir -p /app/logs && \
    mkdir -p /app/config && \
    mkdir -p /app/scripts

# Set correct ownership
RUN chown -R appuser:appgroup /app

# Set different permissions for demonstration (MIRRORS REAL-WORLD ISSUES)
RUN chmod 755 /app && \
    chmod 700 /app/data && \
    chmod 777 /app/logs && \
    chmod 644 /app/config && \
    touch /app/logs/app.log && \
    chmod 777 /app/logs/app.log && \
    touch /app/world_writable.txt && \
    chmod 666 /app/world_writable.txt && \
    touch /app/dangerous_777.sh && \
    chmod 777 /app/dangerous_777.sh && \
    echo '#!/bin/bash\necho "Dangerous script"' > /app/dangerous_777.sh && \
    touch /app/secure_file.txt && \
    chmod 600 /app/secure_file.txt && \
    echo "Secure content" > /app/secure_file.txt && \
    touch /app/config/database.conf && \
    chmod 644 /app/config/database.conf

# Create a setuid binary for testing (real security issue)
RUN echo 'int main() { setuid(0); system("/bin/sh"); }' > /app/test_suid.c && \
    gcc /app/test_suid.c -o /app/scripts/suid_test && \
    chmod 4755 /app/scripts/suid_test 2>/dev/null || true && \
    rm /app/test_suid.c

# Switch to non-root user
USER appuser

# Default to safe dry-run mode (REQUIREMENT: "Fixes with single command (safely)")
CMD ["python3", "-m", "src.auditor", "/app", "-r", "-d", "--format", "human"]

# Add entrypoint script for UID/GID mapping
COPY --chown=appuser:appgroup docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

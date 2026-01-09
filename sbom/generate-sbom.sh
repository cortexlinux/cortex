#!/bin/bash
# Cortex Linux SBOM Generation
# Generates Software Bill of Materials in CycloneDX and SPDX formats
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../output/sbom}"
VERSION="${CORTEX_VERSION:-0.1.0}"
DATE=$(date -Iseconds)
UUID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "00000000-0000-0000-0000-000000000000")

GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $*"; }

mkdir -p "$OUTPUT_DIR"

log "Generating SBOM for Cortex Linux v${VERSION}"

# Generate CycloneDX SBOM
cat > "${OUTPUT_DIR}/cortex-linux-${VERSION}.cdx.json" << EOF
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:${UUID}",
  "version": 1,
  "metadata": {
    "timestamp": "${DATE}",
    "tools": [{"vendor": "AI Venture Holdings LLC", "name": "cortex-sbom-generator", "version": "1.0.0"}],
    "component": {
      "type": "operating-system",
      "name": "Cortex Linux",
      "version": "${VERSION}",
      "description": "AI-Native Linux Distribution",
      "supplier": {"name": "AI Venture Holdings LLC", "url": ["https://cortexlinux.com"]},
      "licenses": [{"license": {"id": "Apache-2.0"}}]
    }
  },
  "components": [
    {"type": "library", "name": "cortex-core", "version": "${VERSION}", "purl": "pkg:deb/cortex/cortex-core@${VERSION}"},
    {"type": "library", "name": "cortex-full", "version": "${VERSION}", "purl": "pkg:deb/cortex/cortex-full@${VERSION}"},
    {"type": "operating-system", "name": "Debian", "version": "13", "purl": "pkg:generic/debian@13"},
    {"type": "library", "name": "python3", "version": "3.11", "purl": "pkg:deb/debian/python3@3.11"},
    {"type": "library", "name": "firejail", "purl": "pkg:deb/debian/firejail"},
    {"type": "library", "name": "apparmor", "purl": "pkg:deb/debian/apparmor"}
  ]
}
EOF

log "CycloneDX: ${OUTPUT_DIR}/cortex-linux-${VERSION}.cdx.json"

# Generate SPDX SBOM
cat > "${OUTPUT_DIR}/cortex-linux-${VERSION}.spdx.json" << EOF
{
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "SPDXID": "SPDXRef-DOCUMENT",
  "name": "Cortex Linux ${VERSION}",
  "documentNamespace": "https://cortexlinux.com/spdx/${VERSION}",
  "creationInfo": {"created": "${DATE}", "creators": ["Organization: AI Venture Holdings LLC", "Tool: cortex-sbom-generator-1.0.0"]},
  "packages": [
    {"SPDXID": "SPDXRef-cortex-linux", "name": "Cortex Linux", "versionInfo": "${VERSION}", "licenseConcluded": "Apache-2.0", "downloadLocation": "https://cortexlinux.com"},
    {"SPDXID": "SPDXRef-cortex-core", "name": "cortex-core", "versionInfo": "${VERSION}", "licenseConcluded": "Apache-2.0", "downloadLocation": "https://repo.cortexlinux.com"},
    {"SPDXID": "SPDXRef-debian", "name": "Debian", "versionInfo": "13", "licenseConcluded": "NOASSERTION", "downloadLocation": "https://debian.org"}
  ],
  "relationships": [
    {"spdxElementId": "SPDXRef-DOCUMENT", "relatedSpdxElement": "SPDXRef-cortex-linux", "relationshipType": "DESCRIBES"},
    {"spdxElementId": "SPDXRef-cortex-linux", "relatedSpdxElement": "SPDXRef-cortex-core", "relationshipType": "CONTAINS"},
    {"spdxElementId": "SPDXRef-cortex-linux", "relatedSpdxElement": "SPDXRef-debian", "relationshipType": "DEPENDS_ON"}
  ]
}
EOF

log "SPDX: ${OUTPUT_DIR}/cortex-linux-${VERSION}.spdx.json"
log "SBOM generation complete"

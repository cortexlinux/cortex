# Cortex Linux Signing Key Management Runbook

## Overview

This document defines the key hierarchy, generation procedures, rotation schedule,
and incident response for Cortex Linux release signing.

## Key Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    OFFLINE ROOT KEY                         │
│              cortex-release-root@cortexlinux.com            │
│                    RSA 4096-bit                             │
│                 Valid: 10 years                             │
│         Storage: Air-gapped, HSM/hardware token             │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      │ Signs
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               ONLINE SIGNING SUBKEYS                         │
├─────────────────────────────────────────────────────────────┤
│  APT Repository Signing Key                                  │
│  cortex-apt-signing@cortexlinux.com                         │
│  RSA 4096-bit | Valid: 2 years | Rotation: Annual           │
├─────────────────────────────────────────────────────────────┤
│  ISO Release Signing Key                                     │
│  cortex-iso-signing@cortexlinux.com                         │
│  RSA 4096-bit | Valid: 2 years | Rotation: Annual           │
├─────────────────────────────────────────────────────────────┤
│  Build Attestation Key                                       │
│  cortex-build-attestation@cortexlinux.com                   │
│  RSA 4096-bit | Valid: 1 year | Rotation: 6 months          │
└─────────────────────────────────────────────────────────────┘
```

## Key Generation Ceremony

### Prerequisites

1. Air-gapped machine (never connected to network)
2. Two or more key ceremony participants
3. Hardware security module (YubiKey 5 or similar)
4. Secure storage for offline root key material
5. Witness log template

### Root Key Generation

```bash
# On air-gapped machine

# 1. Generate root key
export GNUPGHOME=/secure/gnupg
gpg --full-generate-key
# Select: RSA and RSA
# Keysize: 4096
# Validity: 10y
# Name: Cortex Linux Release Signing (Root)
# Email: cortex-release-root@cortexlinux.com

# 2. Generate subkeys
gpg --edit-key cortex-release-root@cortexlinux.com
> addkey
# Select: RSA (sign only)
# Keysize: 4096
# Validity: 2y
# Repeat for each subkey type

# 3. Export public key
gpg --armor --export cortex-release-root@cortexlinux.com > cortex-root.asc

# 4. Export subkeys only (for online signing host)
gpg --armor --export-secret-subkeys cortex-release-root@cortexlinux.com > cortex-subkeys.asc

# 5. Create revocation certificate
gpg --gen-revoke cortex-release-root@cortexlinux.com > cortex-root-revoke.asc

# 6. Backup root key to multiple secure locations
gpg --armor --export-secret-keys cortex-release-root@cortexlinux.com > cortex-root-secret.asc
# Store in safe deposit box, encrypted USB in fireproof safe, etc.
```

### Witness Log

```
CORTEX LINUX KEY CEREMONY LOG
=============================

Date: _______________
Location: _______________
Purpose: Root Key Generation / Key Rotation / Emergency Revocation

PARTICIPANTS:
1. Name: _______________ Role: _______________ Signature: _______________
2. Name: _______________ Role: _______________ Signature: _______________
3. Name: _______________ Role: _______________ Signature: _______________

KEY DETAILS:
- Key ID: _______________
- Fingerprint: _______________
- Creation Date: _______________
- Expiration Date: _______________

ACTIONS PERFORMED:
[ ] Key generated
[ ] Subkeys created
[ ] Revocation certificate created
[ ] Public key exported
[ ] Backup copies created
[ ] Hardware token programmed

STORAGE LOCATIONS:
1. _______________ (custodian: _______________)
2. _______________ (custodian: _______________)

VERIFICATION:
- SHA256 of public key export: _______________
- Witness verification: _______________

Notes:
_______________________________________________
_______________________________________________
```

## Key Rotation Procedure

### Annual Rotation (Subkeys)

1. **Preparation (T-30 days)**
   - Schedule ceremony date
   - Notify stakeholders
   - Prepare new keyring package

2. **Key Generation (T-14 days)**
   - Generate new subkeys from root
   - Sign new subkeys with root
   - Export for online signing host

3. **Overlap Period (T-7 days)**
   - Deploy new subkeys to signing host
   - Update cortex-archive-keyring package
   - Release new keyring to stable-candidate

4. **Transition (T-0)**
   - Promote new keyring to stable
   - Begin signing with new keys
   - Old keys remain valid but unused

5. **Cleanup (T+30 days)**
   - Verify all systems updated
   - Document any issues
   - Archive old subkeys

### Emergency Rotation

Triggered by:
- Suspected key compromise
- Unauthorized signing detected
- Security audit findings

Procedure:
1. **Immediate** (within 1 hour)
   - Disable compromised key on signing host
   - Alert security team
   - Begin incident log

2. **Assessment** (within 4 hours)
   - Determine scope of compromise
   - Identify affected artifacts
   - Plan remediation

3. **Key Replacement** (within 24 hours)
   - Emergency key ceremony
   - Generate new subkeys
   - Deploy to signing infrastructure

4. **Communication** (within 48 hours)
   - Publish security advisory
   - Release new keyring package
   - Notify package maintainers

## APT Keyring Package

### Package Contents

```
cortex-archive-keyring/
├── debian/
│   ├── control
│   ├── rules
│   ├── changelog
│   └── install
└── keyrings/
    └── cortex-archive-keyring.gpg
```

### Building New Keyring Package

```bash
#!/bin/bash
# build-keyring.sh

VERSION="2025.01"
KEYRING_DIR="cortex-archive-keyring"

# Export public keys
gpg --export \
    cortex-release-root@cortexlinux.com \
    cortex-apt-signing@cortexlinux.com \
    > "${KEYRING_DIR}/keyrings/cortex-archive-keyring.gpg"

# Update changelog
dch -v "${VERSION}" "Key rotation: new signing subkey"

# Build package
dpkg-buildpackage -us -uc -b

# Sign package
debsign -k cortex-apt-signing@cortexlinux.com \
    cortex-archive-keyring_${VERSION}_all.changes
```

## Signing Infrastructure

### Online Signing Host Requirements

- Dedicated VM or hardware
- No general SSH access
- Signing operations via CI/CD only
- Subkeys only (no root key)
- Audit logging enabled
- Regular security scans

### GPG Agent Configuration

```
# ~/.gnupg/gpg-agent.conf on signing host

# Require passphrase for each signing operation
default-cache-ttl 0
max-cache-ttl 0

# Use hardware token when available
enable-ssh-support

# Logging
log-file /var/log/gpg-agent.log
verbose
```

### CI/CD Signing Integration

```yaml
# .github/workflows/sign-release.yml (example)

name: Sign Release
on:
  workflow_dispatch:
    inputs:
      artifact:
        description: 'Artifact to sign'
        required: true

jobs:
  sign:
    runs-on: [self-hosted, signing]
    steps:
      - name: Download artifact
        uses: actions/download-artifact@v3

      - name: Sign artifact
        run: |
          gpg --detach-sign --armor \
              -u cortex-apt-signing@cortexlinux.com \
              ${{ inputs.artifact }}

      - name: Upload signature
        uses: actions/upload-artifact@v3
        with:
          name: signatures
          path: "*.asc"
```

## Key Revocation

### Revocation Triggers

- Confirmed key compromise
- Employee departure (key custodian)
- End of key validity period
- Organizational decision

### Revocation Procedure

```bash
# 1. Import revocation certificate
gpg --import cortex-root-revoke.asc

# 2. Publish revoked key
gpg --keyserver keys.openpgp.org --send-keys <KEY_ID>

# 3. Update keyring package to exclude revoked key
# (keep public key with revocation sig for verification)

# 4. Publish security advisory
```

### Post-Revocation Communication

```markdown
# Security Advisory: Key Revocation

**Date:** YYYY-MM-DD
**Severity:** [Critical/High/Medium/Low]
**CVE:** (if applicable)

## Summary

The Cortex Linux signing key [KEY_ID] has been revoked.

## Affected Versions

- cortex-archive-keyring < [new_version]

## Action Required

1. Update keyring: `apt update && apt install cortex-archive-keyring`
2. Verify new key: `gpg --show-keys /usr/share/keyrings/cortex-archive-keyring.gpg`

## Timeline

- [Date]: Issue discovered
- [Date]: Key revoked
- [Date]: New keyring released

## Contact

security@cortexlinux.com
```

## Audit and Compliance

### Regular Audits

- **Weekly**: Review signing logs
- **Monthly**: Verify key inventory
- **Quarterly**: Test revocation procedure
- **Annually**: Full key ceremony audit

### Audit Checklist

```
[ ] All signing operations logged
[ ] Logs reviewed for anomalies
[ ] Key custody verified (all custodians confirmed)
[ ] Backup integrity verified
[ ] Revocation certificates accessible
[ ] Hardware tokens functional
[ ] Documentation current
```

## Contact

- Security Team: security@cortexlinux.com
- Key Custodians: (internal contact list)
- Emergency: (24/7 pager)

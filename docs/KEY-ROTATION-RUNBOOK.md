# Cortex Linux Key Management Runbook

## Overview

This runbook defines procedures for GPG signing key management for Cortex Linux repositories and artifacts.

## Key Hierarchy

```
Cortex Root Key (offline, air-gapped)
├── Repository Signing Subkey (online, rotated annually)
├── ISO Signing Subkey (online, rotated annually)
└── Build Attestation Subkey (CI/CD, rotated quarterly)
```

## Key Specifications

| Key | Algorithm | Expiry | Storage |
|-----|-----------|--------|---------|
| Root Key | RSA 4096 / ed25519 | Never (revocation only) | Air-gapped HSM |
| Repo Signing | RSA 4096 / ed25519 | 2 years | YubiKey / signing server |
| ISO Signing | RSA 4096 / ed25519 | 2 years | YubiKey / signing server |
| Build Attestation | ed25519 | 1 year | CI/CD secrets |

## Key Ceremony: Initial Setup

### Prerequisites
- Air-gapped machine (no network, fresh OS)
- 2+ Hardware Security Modules (HSMs) or YubiKeys
- 2+ trusted witnesses
- Secure storage for backup materials

### Procedure

1. **Prepare Air-Gapped Environment**
   ```bash
   # Boot from live USB (Debian/Tails)
   # Verify no network interfaces
   ip link show
   # All interfaces should be DOWN or absent
   ```

2. **Generate Root Key**
   ```bash
   export GNUPGHOME=$(mktemp -d)
   chmod 700 $GNUPGHOME
   
   gpg --full-generate-key
   # Select: RSA and RSA (default)
   # Keysize: 4096
   # Validity: 0 (does not expire)
   # Real name: Cortex Linux Signing Key
   # Email: security@cortexlinux.com
   # Comment: Root Key
   ```

3. **Generate Signing Subkeys**
   ```bash
   gpg --edit-key security@cortexlinux.com
   
   gpg> addkey
   # Select: RSA (sign only)
   # Keysize: 4096
   # Validity: 2y
   # Purpose: Repository signing
   
   gpg> addkey
   # Repeat for ISO signing subkey
   
   gpg> save
   ```

4. **Export Keys**
   ```bash
   # Export public key (for distribution)
   gpg --armor --export security@cortexlinux.com > cortex-archive-keyring.asc
   
   # Export secret keys (for HSM backup)
   gpg --armor --export-secret-keys security@cortexlinux.com > root-key-secret.asc
   
   # Export subkeys only (for signing servers)
   gpg --armor --export-secret-subkeys security@cortexlinux.com > signing-subkeys.asc
   ```

5. **Backup to HSMs**
   ```bash
   # For each HSM/YubiKey
   gpg --card-edit
   # Transfer keys to card
   ```

6. **Secure Storage**
   - Store root key backup in 2+ geographically separated secure locations
   - Document HSM serial numbers and locations
   - Destroy air-gapped machine storage

7. **Witness Attestation**
   - All witnesses sign ceremony log
   - Store signed logs with key backups

## Key Rotation: Annual Subkey Rotation

### Timeline
- T-30 days: Generate new subkey
- T-14 days: Publish new keyring with both old and new subkeys
- T-0: Begin signing with new subkey
- T+30 days: Old subkey expires (overlap period)

### Procedure

1. **Generate New Subkey**
   ```bash
   # On signing server or with HSM
   gpg --edit-key security@cortexlinux.com
   
   gpg> addkey
   # Create new signing subkey with 2-year validity
   
   gpg> save
   ```

2. **Update Keyring Package**
   ```bash
   # Export updated public key
   gpg --export security@cortexlinux.com > cortex-archive-keyring.gpg
   
   # Update cortex-archive-keyring package
   cd packages/cortex-archive-keyring
   cp cortex-archive-keyring.gpg keys/
   
   # Bump version
   dch -i "Add new signing subkey for 2026"
   
   # Build and publish
   dpkg-buildpackage -us -uc -b
   ```

3. **Publish Updated Keyring**
   ```bash
   # Add to repository
   ./repo-manage.sh add cortex-archive-keyring_*.deb
   ./repo-manage.sh publish
   
   # Announce rotation
   # Update documentation
   ```

4. **Verify Client Updates**
   ```bash
   # After T+7 days, verify update adoption
   # Monitor support tickets for signature issues
   ```

## Key Revocation: Emergency Procedure

### Triggers
- Key compromise confirmed or suspected
- HSM loss or theft
- Unauthorized signing detected

### Immediate Actions (within 1 hour)

1. **Generate Revocation Certificate**
   ```bash
   # If not pre-generated
   gpg --gen-revoke security@cortexlinux.com > revoke.asc
   
   # Apply revocation
   gpg --import revoke.asc
   ```

2. **Publish Revocation**
   ```bash
   # Update keyring immediately
   gpg --export security@cortexlinux.com > cortex-archive-keyring.gpg
   
   # Emergency keyring release
   # Bypass normal release process
   ```

3. **Notify Users**
   - Security advisory on website
   - Email to registered users
   - Social media announcement

4. **Generate New Keys**
   - Follow initial setup ceremony
   - Document incident in new key metadata

### Post-Incident

1. **Root Cause Analysis**
   - Document how compromise occurred
   - Identify affected artifacts

2. **Re-sign Artifacts**
   - Re-sign all repository metadata
   - Re-sign all ISO images
   - Update all checksums

3. **Update Procedures**
   - Document lessons learned
   - Update this runbook

## Key Storage Locations

| Key Material | Primary Location | Backup Location |
|--------------|------------------|-----------------|
| Root Private Key | Safe deposit box A | Safe deposit box B |
| Root HSM 1 | CEO secure storage | - |
| Root HSM 2 | CTO secure storage | - |
| Signing Subkeys | Signing server HSM | Backup HSM |
| Revocation Certs | With root backups | Separate secure storage |

## Contacts

| Role | Contact |
|------|---------|
| Key Custodian 1 | security@cortexlinux.com |
| Key Custodian 2 | cto@cortexlinux.com |
| Security Team | security@cortexlinux.com |
| Emergency | +1-XXX-XXX-XXXX |

## Audit Schedule

- Monthly: Verify signing server access logs
- Quarterly: Verify HSM inventory
- Annually: Full key ceremony audit
- After incidents: Post-incident review

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-08 | Cortex Team | Initial runbook |

# Cortex Linux Hardware Compatibility Matrix

## Overview

This document defines the certified hardware profiles for Cortex Linux and the validation status for each component.

## Certified Server Profiles

### Profile 1: Dell PowerEdge (Intel)

| Component | Model | Status | Notes |
|-----------|-------|--------|-------|
| Server | Dell PowerEdge R750 | ✅ Certified | Reference platform |
| CPU | Intel Xeon Scalable 4th Gen | ✅ Certified | Ice Lake / Sapphire Rapids |
| NIC | Intel X710 / E810 | ✅ Certified | In-tree drivers |
| Storage | PERC H755 | ✅ Certified | megaraid_sas |
| RAID | Dell PERC | ✅ Certified | |
| GPU | NVIDIA A100/L40 | ✅ Certified | Optional |
| BMC | iDRAC 9 | ✅ Certified | IPMI |

### Profile 2: HPE ProLiant (Intel)

| Component | Model | Status | Notes |
|-----------|-------|--------|-------|
| Server | HPE ProLiant DL380 Gen11 | ✅ Certified | |
| CPU | Intel Xeon Scalable 4th Gen | ✅ Certified | |
| NIC | HPE Ethernet 10/25Gb 2-port | ✅ Certified | |
| Storage | HPE Smart Array | ✅ Certified | |
| GPU | NVIDIA A100/H100 | ✅ Certified | Optional |
| BMC | HPE iLO 6 | ✅ Certified | |

### Profile 3: Supermicro (AMD)

| Component | Model | Status | Notes |
|-----------|-------|--------|-------|
| Server | Supermicro H13 Series | ✅ Certified | |
| CPU | AMD EPYC 9004 | ✅ Certified | Genoa |
| NIC | Mellanox ConnectX-6 | ✅ Certified | mlx5 |
| Storage | Broadcom MegaRAID | ✅ Certified | |
| GPU | AMD MI200/MI300 | ⚠️ Testing | ROCm |
| BMC | IPMI 2.0 | ✅ Certified | |

### Profile 4: Generic VM (KVM/QEMU)

| Component | Model | Status | Notes |
|-----------|-------|--------|-------|
| Platform | KVM/QEMU | ✅ Certified | Primary test target |
| CPU | virtio-cpu | ✅ Certified | |
| NIC | virtio-net | ✅ Certified | |
| Storage | virtio-blk/scsi | ✅ Certified | |
| Display | virtio-gpu | ✅ Certified | |
| RNG | virtio-rng | ✅ Certified | |

### Profile 5: Proxmox VE

| Component | Model | Status | Notes |
|-----------|-------|--------|-------|
| Platform | Proxmox VE 8.x | ✅ Certified | |
| CPU | Host passthrough | ✅ Certified | |
| NIC | virtio | ✅ Certified | |
| Storage | virtio-scsi | ✅ Certified | |
| GPU | PCIe Passthrough | ⚠️ Testing | NVIDIA/AMD |

## NIC Compatibility

| Vendor | Model | Driver | Status |
|--------|-------|--------|--------|
| Intel | X710 | i40e | ✅ Certified |
| Intel | E810 | ice | ✅ Certified |
| Intel | I350 | igb | ✅ Certified |
| Intel | X550 | ixgbe | ✅ Certified |
| Mellanox | ConnectX-5 | mlx5_core | ✅ Certified |
| Mellanox | ConnectX-6 | mlx5_core | ✅ Certified |
| Broadcom | NetXtreme BCM57xx | tg3 | ✅ Certified |
| Broadcom | NetXtreme-E | bnxt_en | ✅ Certified |
| Realtek | RTL8125 | r8169 | ⚠️ Community |

## Storage Controller Compatibility

| Vendor | Model | Driver | Status |
|--------|-------|--------|--------|
| Broadcom | MegaRAID SAS | megaraid_sas | ✅ Certified |
| Broadcom | HBA 9500 | mpt3sas | ✅ Certified |
| Dell | PERC H7xx | megaraid_sas | ✅ Certified |
| HPE | Smart Array | hpsa | ✅ Certified |
| Intel | VROC | md/raid | ✅ Certified |
| NVMe | Generic | nvme | ✅ Certified |
| AHCI | Generic | ahci | ✅ Certified |

## GPU Compatibility

### NVIDIA GPUs

| Model | Architecture | CUDA | Status |
|-------|--------------|------|--------|
| H100 | Hopper | 9.0 | ✅ Certified |
| H200 | Hopper | 9.0 | ✅ Certified |
| A100 | Ampere | 8.0 | ✅ Certified |
| A30 | Ampere | 8.0 | ✅ Certified |
| A40 | Ampere | 8.6 | ✅ Certified |
| L40 | Ada | 8.9 | ✅ Certified |
| T4 | Turing | 7.5 | ✅ Certified |
| V100 | Volta | 7.0 | ✅ Certified |
| RTX 4090 | Ada | 8.9 | ⚠️ Community |

### AMD GPUs

| Model | Architecture | ROCm | Status |
|-------|--------------|------|--------|
| MI300A | CDNA 3 | 6.0 | ⚠️ Testing |
| MI250X | CDNA 2 | 6.0 | ⚠️ Testing |
| MI210 | CDNA 2 | 6.0 | ⚠️ Testing |
| MI100 | CDNA | 5.0 | ⚠️ Testing |

## Firmware Requirements

| Component | Minimum Version | Recommended |
|-----------|-----------------|-------------|
| Linux Kernel | 6.1 | 6.6+ |
| Intel Microcode | 20231114 | Latest |
| AMD Microcode | 20231111 | Latest |
| NVIDIA Driver | 535 | 550+ |
| ROCm | 5.7 | 6.0+ |

## Boot Modes

| Mode | Status | Notes |
|------|--------|-------|
| UEFI | ✅ Certified | Primary |
| Legacy BIOS | ⚠️ Community | Best-effort |
| Secure Boot | ✅ Certified | With MOK for DKMS |

## Test Matrix

Each certified profile undergoes:

1. **Install Tests**
   - [ ] Boot from ISO (UEFI)
   - [ ] Boot from ISO (BIOS)
   - [ ] Preseed automated install
   - [ ] Network detection
   - [ ] Storage detection
   - [ ] LVM partitioning
   - [ ] Encryption (LUKS)

2. **First Boot Tests**
   - [ ] Firstboot service completes
   - [ ] Network connectivity
   - [ ] SSH access
   - [ ] APT repository access
   - [ ] GPU detection (if present)

3. **Upgrade Tests**
   - [ ] apt upgrade (minor)
   - [ ] Kernel upgrade
   - [ ] Cortex upgrade
   - [ ] Rollback capability

4. **Stress Tests**
   - [ ] 72-hour runtime stability
   - [ ] Memory stress (memtest)
   - [ ] Storage stress (fio)
   - [ ] Network stress (iperf3)

## Reporting Issues

Hardware compatibility issues should be reported to:
- GitHub: https://github.com/cortexlinux/cortex-distro/issues
- Label: `hardware-compatibility`

Include:
- Hardware model and firmware version
- `lspci -vvnn` output
- `dmesg` output
- `journalctl -b` output

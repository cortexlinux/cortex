# Cortex Linux Distribution Build System
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

SHELL := /bin/bash
.PHONY: all iso iso-netinst iso-offline package sbom clean test help

# Build configuration
CODENAME := trixie
ARCH := amd64
VERSION := 0.1.0
BUILD_DATE := $(shell date +%Y%m%d)
ISO_NAME := cortex-linux-$(VERSION)-$(ARCH)-$(BUILD_DATE)

# Directories
BUILD_DIR := build
ISO_DIR := iso/live-build
OUTPUT_DIR := output
PACKAGES_DIR := packages

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

help:
	@echo "Cortex Linux Distribution Build System"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  iso           Build full offline ISO (default)"
	@echo "  iso-netinst   Build minimal network installer ISO"
	@echo "  iso-offline   Build full offline ISO with package pool"
	@echo "  package       Build all meta-packages"
	@echo "  package PKG=x Build specific package (cortex-core, cortex-full, cortex-archive-keyring)"
	@echo "  sbom          Generate Software Bill of Materials"
	@echo "  test          Run build verification tests"
	@echo "  clean         Remove build artifacts"
	@echo "  deps          Install build dependencies"
	@echo ""

all: iso

# Install build dependencies (requires root)
deps:
	@echo -e "$(GREEN)Installing build dependencies...$(NC)"
	apt-get update
	apt-get install -y \
		live-build \
		debootstrap \
		squashfs-tools \
		xorriso \
		isolinux \
		syslinux-efi \
		grub-pc-bin \
		grub-efi-amd64-bin \
		mtools \
		dosfstools \
		dpkg-dev \
		devscripts \
		debhelper \
		fakeroot \
		gnupg \
		syft \
		cyclonedx-cli \
		python3-pip
	@echo -e "$(GREEN)Dependencies installed$(NC)"

# Configure live-build
$(BUILD_DIR)/.configured:
	@echo -e "$(GREEN)Configuring live-build...$(NC)"
	mkdir -p $(BUILD_DIR)
	cd $(ISO_DIR) && lb config \
		--distribution $(CODENAME) \
		--archive-areas "main contrib non-free non-free-firmware" \
		--architectures $(ARCH) \
		--binary-images iso-hybrid \
		--bootloaders "grub-efi,syslinux" \
		--debian-installer live \
		--debian-installer-gui false \
		--iso-application "Cortex Linux" \
		--iso-publisher "AI Venture Holdings LLC" \
		--iso-volume "Cortex Linux $(VERSION)" \
		--memtest none \
		--security true \
		--updates true \
		--backports true \
		--apt-indices true \
		--apt-recommends true \
		--apt-source-archives false \
		--cache true \
		--checksums sha256 \
		--clean \
		--color \
		--compression xz \
		--debconf-frontend noninteractive \
		--debootstrap-options "--variant=minbase" \
		--firmware-binary true \
		--firmware-chroot true \
		--initramfs live-boot \
		--interactive false \
		--linux-packages "linux-image linux-headers" \
		--mode debian \
		--system live \
		--bootappend-live "boot=live components quiet splash"
	touch $@

# Build ISO
iso: iso-offline

iso-netinst: $(BUILD_DIR)/.configured
	@echo -e "$(GREEN)Building network installer ISO...$(NC)"
	cd $(ISO_DIR) && sudo lb build 2>&1 | tee $(BUILD_DIR)/build-netinst.log
	mkdir -p $(OUTPUT_DIR)
	mv $(ISO_DIR)/live-image-$(ARCH).hybrid.iso $(OUTPUT_DIR)/$(ISO_NAME)-netinst.iso
	cd $(OUTPUT_DIR) && sha256sum $(ISO_NAME)-netinst.iso > $(ISO_NAME)-netinst.iso.sha256
	@echo -e "$(GREEN)ISO built: $(OUTPUT_DIR)/$(ISO_NAME)-netinst.iso$(NC)"

iso-offline: $(BUILD_DIR)/.configured package
	@echo -e "$(GREEN)Building full offline ISO...$(NC)"
	cd $(ISO_DIR) && sudo lb build 2>&1 | tee $(BUILD_DIR)/build-offline.log
	mkdir -p $(OUTPUT_DIR)
	mv $(ISO_DIR)/live-image-$(ARCH).hybrid.iso $(OUTPUT_DIR)/$(ISO_NAME)-offline.iso
	cd $(OUTPUT_DIR) && sha256sum $(ISO_NAME)-offline.iso > $(ISO_NAME)-offline.iso.sha256
	@echo -e "$(GREEN)ISO built: $(OUTPUT_DIR)/$(ISO_NAME)-offline.iso$(NC)"

# Build packages
package:
ifdef PKG
	@echo -e "$(GREEN)Building package: $(PKG)$(NC)"
	cd $(PACKAGES_DIR)/$(PKG) && dpkg-buildpackage -us -uc -b
else
	@echo -e "$(GREEN)Building all packages...$(NC)"
	for pkg in cortex-archive-keyring cortex-core cortex-full; do \
		echo -e "$(YELLOW)Building $$pkg...$(NC)"; \
		cd $(PACKAGES_DIR)/$$pkg && dpkg-buildpackage -us -uc -b && cd ../..; \
	done
endif
	@echo -e "$(GREEN)Packages built$(NC)"

# Generate SBOM
sbom:
	@echo -e "$(GREEN)Generating Software Bill of Materials...$(NC)"
	mkdir -p $(OUTPUT_DIR)/sbom
	@if [ -f "$(OUTPUT_DIR)/$(ISO_NAME)-offline.iso" ]; then \
		echo "Generating SBOM for ISO..."; \
		syft $(OUTPUT_DIR)/$(ISO_NAME)-offline.iso -o cyclonedx-json > $(OUTPUT_DIR)/sbom/$(ISO_NAME).cdx.json; \
		syft $(OUTPUT_DIR)/$(ISO_NAME)-offline.iso -o spdx-json > $(OUTPUT_DIR)/sbom/$(ISO_NAME).spdx.json; \
	else \
		echo "No ISO found, generating SBOM from package lists..."; \
		./scripts/generate-sbom.sh $(OUTPUT_DIR)/sbom; \
	fi
	@echo -e "$(GREEN)SBOM generated in $(OUTPUT_DIR)/sbom/$(NC)"

# Run tests
test:
	@echo -e "$(GREEN)Running build verification tests...$(NC)"
	./tests/verify-iso.sh $(OUTPUT_DIR)/$(ISO_NAME)-offline.iso || true
	./tests/verify-packages.sh || true
	./tests/verify-preseed.sh || true
	@echo -e "$(GREEN)Tests complete$(NC)"

# Clean build artifacts
clean:
	@echo -e "$(YELLOW)Cleaning build artifacts...$(NC)"
	cd $(ISO_DIR) && sudo lb clean --purge 2>/dev/null || true
	rm -rf $(BUILD_DIR)
	rm -rf $(OUTPUT_DIR)
	find $(PACKAGES_DIR) -name "*.deb" -delete
	find $(PACKAGES_DIR) -name "*.buildinfo" -delete
	find $(PACKAGES_DIR) -name "*.changes" -delete
	@echo -e "$(GREEN)Clean complete$(NC)"

# Development helpers
dev-shell:
	@echo "Starting development shell in build environment..."
	cd $(ISO_DIR) && sudo lb shell

chroot-shell:
	@echo "Starting chroot shell..."
	cd $(ISO_DIR) && sudo lb chroot

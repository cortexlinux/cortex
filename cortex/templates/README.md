# Installation Templates

This directory contains built-in installation templates for common development stacks.

## Available Templates

- **lamp.yaml** - LAMP Stack (Linux, Apache, MySQL, PHP)
- **mean.yaml** - MEAN Stack (MongoDB, Express.js, Angular, Node.js)
- **mern.yaml** - MERN Stack (MongoDB, Express.js, React, Node.js)
- **ml-ai.yaml** - Machine Learning / AI Stack
- **devops.yaml** - DevOps Stack (Docker, Kubernetes, Terraform, etc.)

## Usage

```bash
# List all templates
cortex template list

# Install from template
cortex install --template lamp --execute

# Create custom template
cortex template create my-stack

# Import template
cortex template import my-template.yaml

# Export template
cortex template export lamp my-lamp.yaml
```

## Template Format

Templates are defined in YAML format with the following structure:

```yaml
name: Template Name
description: Template description
version: 1.0.0
author: Author Name (optional)

packages:
  - package1
  - package2

steps:
  - command: apt update
    description: Update packages
    requires_root: true
    rollback: (optional)

hardware_requirements:
  min_ram_mb: 2048
  min_cores: 2
  min_storage_mb: 10240

post_install:
  - echo "Installation complete"

verification_commands:
  - package --version
```

See [TEMPLATES.md](../../docs/TEMPLATES.md) for complete documentation.


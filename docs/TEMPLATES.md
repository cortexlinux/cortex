# Installation Templates Guide

Cortex Linux provides a powerful template system for installing common development stacks and software bundles. Templates are pre-configured installation definitions that can be shared, customized, and reused.

## Overview

Templates allow you to:
- Install complete development stacks with a single command
- Share installation configurations with your team
- Create custom templates for your specific needs
- Validate hardware compatibility before installation
- Export and import templates for easy sharing

## Quick Start

### Installing from a Template

```bash
# List available templates
cortex template list

# Install LAMP stack
cortex install --template lamp --execute

# Install MEAN stack (dry run first)
cortex install --template mean --dry-run
cortex install --template mean --execute
```

### Creating a Custom Template

```bash
# Create a new template interactively
cortex template create my-stack

# Import a template from file
cortex template import my-template.yaml

# Export a template
cortex template export lamp my-lamp-template.yaml
```

## Built-in Templates

Cortex Linux comes with 5+ pre-built templates:

### 1. LAMP Stack

Linux, Apache, MySQL, PHP stack for traditional web development.

```bash
cortex install --template lamp --execute
```

**Packages:**
- Apache 2.4
- MySQL 8.0
- PHP 8.2
- phpMyAdmin

**Hardware Requirements:**
- Minimum RAM: 1GB
- Minimum CPU cores: 2
- Minimum storage: 5GB

**Access:**
- Apache: http://localhost
- phpMyAdmin: http://localhost/phpmyadmin

### 2. MEAN Stack

MongoDB, Express.js, Angular, Node.js stack for modern web applications.

```bash
cortex install --template mean --execute
```

**Packages:**
- Node.js 20.x
- MongoDB
- Angular CLI
- Express generator

**Hardware Requirements:**
- Minimum RAM: 2GB
- Minimum CPU cores: 2
- Minimum storage: 10GB

### 3. MERN Stack

MongoDB, Express.js, React, Node.js stack for full-stack JavaScript development.

```bash
cortex install --template mern --execute
```

**Packages:**
- Node.js 20.x
- MongoDB
- React (via create-react-app)
- Express generator

**Hardware Requirements:**
- Minimum RAM: 2GB
- Minimum CPU cores: 2
- Minimum storage: 10GB

### 4. ML/AI Stack

Machine Learning and Artificial Intelligence development stack.

```bash
cortex install --template ml-ai --execute
```

**Packages:**
- Python 3.x
- NumPy, Pandas, SciPy
- TensorFlow
- PyTorch
- Jupyter Notebook
- Scikit-learn
- Matplotlib, Seaborn

**Hardware Requirements:**
- Minimum RAM: 4GB
- Minimum CPU cores: 4
- Minimum storage: 20GB

### 5. DevOps Stack

Complete DevOps toolchain with containerization and infrastructure tools.

```bash
cortex install --template devops --execute
```

**Packages:**
- Docker & Docker Compose
- Kubernetes (kubectl)
- Terraform
- Ansible
- Git
- Jenkins (optional)

**Hardware Requirements:**
- Minimum RAM: 4GB
- Minimum CPU cores: 4
- Minimum storage: 20GB

## Template Format

Templates are defined in YAML or JSON format. Here's the structure:

### YAML Format

```yaml
name: My Custom Stack
description: A custom development stack
version: 1.0.0
author: Your Name

packages:
  - package1
  - package2
  - package3

steps:
  - command: apt update
    description: Update package lists
    requires_root: true
  - command: apt install -y package1 package2
    description: Install packages
    requires_root: true
    rollback: apt remove -y package1 package2

hardware_requirements:
  min_ram_mb: 2048
  min_cores: 2
  min_storage_mb: 10240
  requires_gpu: false
  requires_cuda: false

post_install:
  - echo "Stack installed successfully"
  - echo "Access at: http://localhost"

verification_commands:
  - package1 --version
  - systemctl is-active service1

metadata:
  category: web-development
  tags:
    - web
    - server
```

### JSON Format

```json
{
  "name": "My Custom Stack",
  "description": "A custom development stack",
  "version": "1.0.0",
  "author": "Your Name",
  "packages": [
    "package1",
    "package2"
  ],
  "steps": [
    {
      "command": "apt update",
      "description": "Update package lists",
      "requires_root": true
    }
  ],
  "hardware_requirements": {
    "min_ram_mb": 2048,
    "min_cores": 2,
    "min_storage_mb": 10240
  },
  "post_install": [
    "echo 'Stack installed successfully'"
  ],
  "verification_commands": [
    "package1 --version"
  ]
}
```

## Template Fields

### Required Fields

- **name**: Template name (string)
- **description**: Template description (string)
- **version**: Template version (string, e.g., "1.0.0")

### Optional Fields

- **author**: Template author (string)
- **packages**: List of package names (array of strings)
- **steps**: Installation steps (array of step objects)
- **hardware_requirements**: Hardware requirements (object)
- **post_install**: Post-installation commands (array of strings)
- **verification_commands**: Commands to verify installation (array of strings)
- **metadata**: Additional metadata (object)

### Installation Steps

Each step can have:
- **command**: Command to execute (required)
- **description**: Step description (required)
- **rollback**: Rollback command (optional)
- **verify**: Verification command (optional)
- **requires_root**: Whether root is required (boolean, default: true)

### Hardware Requirements

- **min_ram_mb**: Minimum RAM in megabytes (integer)
- **min_cores**: Minimum CPU cores (integer)
- **min_storage_mb**: Minimum storage in megabytes (integer)
- **requires_gpu**: Whether GPU is required (boolean)
- **gpu_vendor**: Required GPU vendor ("NVIDIA", "AMD", "Intel")
- **requires_cuda**: Whether CUDA is required (boolean)
- **min_cuda_version**: Minimum CUDA version (string, e.g., "11.0")

## Creating Custom Templates

### Interactive Creation

```bash
cortex template create my-stack
```

This will prompt you for:
- Description
- Version
- Author (optional)
- Packages (one per line)
- Hardware requirements (optional)

### Manual Creation

1. Create a YAML or JSON file:

```yaml
name: my-custom-stack
description: My custom development stack
version: 1.0.0
packages:
  - python3
  - nodejs
  - docker
```

2. Import the template:

```bash
cortex template import my-template.yaml
```

3. Use the template:

```bash
cortex install --template my-custom-stack --execute
```

## Template Management

### Listing Templates

```bash
cortex template list
```

Output:
```
📋 Available Templates:
================================================================================
Name                 Version       Type         Description                          
================================================================================
devops               1.0.0         built-in     Complete DevOps toolchain...
lamp                 1.0.0         built-in     Linux, Apache, MySQL, PHP...
mean                 1.0.0         built-in     MongoDB, Express.js, Angular...
mern                 1.0.0         built-in     MongoDB, Express.js, React...
ml-ai                1.0.0         built-in     Machine Learning and AI...

Total: 5 templates
```

### Exporting Templates

```bash
# Export to YAML (default)
cortex template export lamp my-lamp-template.yaml

# Export to JSON
cortex template export lamp my-lamp-template.json --format json
```

### Importing Templates

```bash
# Import with original name
cortex template import my-template.yaml

# Import with custom name
cortex template import my-template.yaml --name my-custom-name
```

## Hardware Compatibility

Templates can specify hardware requirements. Cortex will check compatibility before installation:

```bash
$ cortex install --template ml-ai --execute

📋 ML/AI Stack Template:
   Machine Learning and Artificial Intelligence development stack

   Packages:
   - python3
   - python3-pip
   ...

⚠️  Hardware Compatibility Warnings:
   - Insufficient RAM: 2048MB available, 4096MB required

⚠️  Hardware requirements not met. Continue anyway? (y/N):
```

## Template Validation

Templates are automatically validated before installation. Validation checks:

- Required fields are present
- At least packages or steps are defined
- Step commands and descriptions are provided
- Hardware requirements are valid (non-negative values)
- CUDA requirements are consistent with GPU requirements

## Example Templates

### Python Data Science Stack

```yaml
name: Python Data Science
description: Python with data science libraries
version: 1.0.0
packages:
  - python3
  - python3-pip
  - python3-venv
steps:
  - command: pip3 install numpy pandas scipy matplotlib jupyter scikit-learn
    description: Install data science libraries
    requires_root: false
hardware_requirements:
  min_ram_mb: 2048
  min_cores: 2
```

### Docker Development Stack

```yaml
name: Docker Development
description: Docker with development tools
version: 1.0.0
packages:
  - docker.io
  - docker-compose
  - git
steps:
  - command: systemctl start docker
    description: Start Docker service
    requires_root: true
    rollback: systemctl stop docker
  - command: systemctl enable docker
    description: Enable Docker on boot
    requires_root: true
verification_commands:
  - docker --version
  - docker ps
```

### Full-Stack Web Development

```yaml
name: Full-Stack Web
description: Complete web development environment
version: 1.0.0
packages:
  - nodejs
  - npm
  - python3
  - postgresql
  - redis-server
  - nginx
steps:
  - command: npm install -g yarn typescript
    description: Install global Node.js tools
    requires_root: false
  - command: systemctl start postgresql
    description: Start PostgreSQL
    requires_root: true
  - command: systemctl start redis
    description: Start Redis
    requires_root: true
hardware_requirements:
  min_ram_mb: 4096
  min_cores: 4
post_install:
  - echo "Web development stack ready!"
  - echo "PostgreSQL: localhost:5432"
  - echo "Redis: localhost:6379"
```

## Best Practices

1. **Always test templates in dry-run mode first:**
   ```bash
   cortex install --template my-template --dry-run
   ```

2. **Specify hardware requirements** to help users understand system needs

3. **Include verification commands** to ensure installation succeeded

4. **Add rollback commands** for critical steps to enable safe rollback

5. **Use descriptive step descriptions** for better user experience

6. **Version your templates** to track changes

7. **Document post-installation steps** in post_install commands

## Troubleshooting

### Template Not Found

If a template is not found, check:
- Template name is correct (use `cortex template list` to verify)
- Template file exists in `~/.cortex/templates/` or built-in templates directory
- File extension is `.yaml`, `.yml`, or `.json`

### Validation Errors

If template validation fails:
- Check all required fields are present
- Ensure at least packages or steps are defined
- Verify hardware requirements are non-negative
- Check step commands and descriptions are provided

### Hardware Compatibility Warnings

If hardware compatibility warnings appear:
- Review the warnings carefully
- Consider if the installation will work with your hardware
- Some templates may work with less hardware but with reduced performance
- You can proceed anyway if you understand the risks

## Template Sharing

Templates can be shared by:
1. Exporting to a file
2. Sharing the file via version control, email, or file sharing
3. Importing on another system

Example workflow:
```bash
# On source system
cortex template export my-stack my-stack.yaml

# Share my-stack.yaml

# On target system
cortex template import my-stack.yaml
cortex install --template my-stack --execute
```

## Advanced Usage

### Using Steps Instead of Packages

For more control, use explicit installation steps:

```yaml
steps:
  - command: apt update
    description: Update package lists
  - command: curl -fsSL https://get.docker.com | sh
    description: Install Docker
    rollback: apt remove -y docker docker-engine
  - command: systemctl start docker
    description: Start Docker service
    verify: systemctl is-active docker
```

### Conditional Installation

While templates don't support conditional logic directly, you can use shell commands:

```yaml
steps:
  - command: |
      if [ ! -f /usr/bin/docker ]; then
        apt install -y docker.io
      fi
    description: Install Docker if not present
```

### Post-Installation Configuration

Use post_install commands for configuration:

```yaml
post_install:
  - echo "Configuring service..."
  - systemctl enable myservice
  - echo "Service configured. Access at http://localhost:8080"
```

## See Also

- [User Guide](../User-Guide.md) - General Cortex usage
- [Developer Guide](../Developer-Guide.md) - Contributing to Cortex
- [Getting Started](../Getting-Started.md) - Quick start guide


# Configuration File Template System

## 📋 Overview

A production-ready system to generate common configuration files from templates with validation, backup support, and clean code architecture.

## ✅ Acceptance Criteria - ALL MET

- ✅ **4+ config types supported**: Nginx, PostgreSQL, Redis, Docker Compose, Apache (5 types)
- ✅ **Valid output**: All configurations validated before writing
- ✅ **Tests**: 28 comprehensive tests with 100% pass rate
- ✅ **Documentation**: Complete README, examples, and inline documentation

## 🎯 Features

### Core Functionality
- **5 Configuration Types**: nginx, PostgreSQL, Redis, Docker Compose, Apache
- **Jinja2 Template Engine**: Powerful variable substitution and conditional logic
- **Pre-Write Validation**: Each config type has custom validators
- **Automatic Backups**: Backs up existing configurations with timestamps
- **Dry Run Mode**: Preview configurations without writing files
- **Cross-Platform**: Works on Windows, Linux, and macOS
- **Clean Code**: PEP 8 compliant, well-documented, modular architecture

### Configuration Types

#### 1. Nginx
- Reverse proxy configurations
- Static web server setups
- SSL/TLS support
- Gzip compression
- Custom logging

#### 2. PostgreSQL
- Connection settings
- Memory optimization
- Replication setup
- SSL configuration
- Query tuning

#### 3. Redis
- Network configuration
- Persistence settings
- Replication
- Memory management
- Security settings

#### 4. Docker Compose
- Multi-service orchestration
- Network configuration
- Volume management
- Health checks
- Build configurations

#### 5. Apache
- Reverse proxy
- Static hosting
- SSL/TLS
- Virtual hosts
- Proxy timeouts

## 🚀 Quick Start

```python
from cortex.config import ConfigGenerator

# Create generator instance
cg = ConfigGenerator()

# Generate nginx reverse proxy
cg.generate(
    "nginx",
    reverse_proxy=True,
    target_port=3000,
    server_name="app.example.com"
)

# Creates: nginx configuration with validation and backup
```

## 📁 Project Structure

```
cortex/
├── __init__.py                     # Package initialization
├── config/
│   ├── __init__.py                 # Config module initialization
│   ├── generator.py                # Main ConfigGenerator class
│   ├── validators.py               # Configuration validators
│   ├── exceptions.py               # Custom exceptions
│   ├── requirements.txt            # Dependencies
│   ├── README.md                   # Comprehensive documentation
│   ├── examples.py                 # 12 working examples
│   ├── test_config_generator.py    # 28 comprehensive tests
│   └── templates/                  # Configuration templates
│       ├── nginx.conf.template
│       ├── postgresql.conf.template
│       ├── redis.conf.template
│       ├── docker-compose.yml.template
│       └── apache.conf.template
```

## 🔧 Installation

```bash
# Navigate to project directory
cd cortex

# Install dependencies
pip install -r cortex/config/requirements.txt

# Or install specific packages
pip install jinja2 pytest pytest-cov
```

## 📚 Usage Examples

### Example 1: Nginx Reverse Proxy
```python
from cortex.config import ConfigGenerator

cg = ConfigGenerator()
cg.generate(
    "nginx",
    reverse_proxy=True,
    target_port=3000,
    server_name="api.example.com",
    ssl_enabled=True,
    ssl_certificate="/etc/ssl/certs/server.crt",
    ssl_certificate_key="/etc/ssl/private/server.key"
)
```

### Example 2: PostgreSQL Database
```python
cg.generate(
    "postgres",
    port=5432,
    max_connections=200,
    shared_buffers="256MB",
    effective_cache_size="8GB",
    enable_replication=True
)
```

### Example 3: Docker Compose Stack
```python
services = [
    {
        "name": "web",
        "image": "nginx:latest",
        "ports": ["80:80"],
        "depends_on": ["api"]
    },
    {
        "name": "api",
        "build": {"context": "./api"},
        "ports": ["3000:3000"],
        "environment": {"NODE_ENV": "production"}
    },
    {
        "name": "db",
        "image": "postgres:13",
        "environment": {
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "myapp"
        }
    }
]

cg.generate(
    "docker-compose",
    version="3.8",
    services=services,
    networks={"app_network": {"driver": "bridge"}}
)
```

### Example 4: Redis Cache
```python
cg.generate(
    "redis",
    port=6379,
    maxmemory="1gb",
    maxmemory_policy="allkeys-lru",
    persistence=True,
    enable_protected_mode=True
)
```

### Example 5: Dry Run (Preview)
```python
# Preview without writing
config = cg.generate(
    "nginx",
    dry_run=True,
    reverse_proxy=True,
    target_port=5000
)
print(config)
```

## 🧪 Testing

```bash
# Run all tests
pytest cortex/config/test_config_generator.py -v

# Run with coverage
pytest cortex/config/test_config_generator.py --cov=cortex.config --cov-report=html

# Run specific test
pytest cortex/config/test_config_generator.py::TestConfigGenerator::test_nginx_reverse_proxy_generation -v
```

### Test Results
```
============================= 28 passed in 0.79s ==============================
```

**Test Coverage:**
- ConfigGenerator initialization ✅
- Template listing and info ✅
- All 5 config type generation ✅
- SSL/TLS configurations ✅
- Backup and restore ✅
- Validation (enabled/disabled) ✅
- Dry run mode ✅
- Custom variables ✅
- Error handling ✅
- All 5 validators ✅

## 📖 Documentation

Complete documentation available in:
- `cortex/config/README.md` - Comprehensive guide with all parameters
- `cortex/config/examples.py` - 12 working examples
- Inline documentation - All classes and methods documented

## 🏗️ Architecture

### Class Diagram
```
ConfigGenerator
├── Template Management
│   ├── Jinja2 Environment
│   ├── Template Loading
│   └── Variable Substitution
├── Validation System
│   ├── NginxValidator
│   ├── PostgresValidator
│   ├── RedisValidator
│   ├── DockerComposeValidator
│   └── ApacheValidator
├── Backup System
│   ├── Automatic Backup
│   ├── Timestamp Management
│   └── Restore Functionality
└── File Operations
    ├── Safe Writing
    ├── Permission Handling
    └── Path Management
```

### Design Patterns
- **Template Method Pattern**: Base validator with specific implementations
- **Strategy Pattern**: Different validation strategies per config type
- **Factory Pattern**: Validator registry for config types
- **Dependency Injection**: Configurable paths and options

## 🔒 Validation

Each configuration type has comprehensive validation:

### Nginx Validator
- Server block structure
- Port ranges (1-65535)
- SSL certificate paths
- Listen directives

### PostgreSQL Validator
- Port ranges
- Memory format validation
- Common settings presence
- SSL configuration

### Redis Validator
- Port ranges
- Memory format
- Persistence consistency
- Bind address

### Docker Compose Validator
- Services definition
- Version format
- Image names
- Network configuration

### Apache Validator
- VirtualHost structure
- DocumentRoot (for static sites)
- Port ranges
- SSL completeness

## 🛡️ Error Handling

Custom exception hierarchy:
```python
ConfigError (base)
├── ValidationError    # Validation failures
├── TemplateError     # Template processing errors
└── BackupError       # Backup/restore failures
```

Example:
```python
from cortex.config import ConfigGenerator
from cortex.config.exceptions import ValidationError

try:
    cg = ConfigGenerator()
    cg.generate("nginx", port=99999)  # Invalid port
except ValidationError as e:
    print(f"Validation failed: {e}")
```

## 🎨 Code Quality

- **PEP 8 Compliant**: Clean, readable Python code
- **Type Hints**: Full type annotations for better IDE support
- **Documentation**: Comprehensive docstrings
- **Modular**: Separated concerns (generator, validators, exceptions)
- **Testable**: High test coverage with pytest
- **Cross-Platform**: Windows and Unix compatibility

## 📊 Performance

- **Fast Template Rendering**: Jinja2 optimized templates
- **Lazy Loading**: Templates loaded on demand
- **Efficient Validation**: Early exit on critical errors
- **Minimal Dependencies**: Only Jinja2 and pytest

## 🔄 Backup System

Automatic backup features:
- Timestamps in format: `filename.YYYYMMDD_HHMMSS.backup`
- Stored in `~/.cortex/backups/` by default
- List all backups: `cg.list_backups()`
- Restore: `cg.restore_backup("nginx", "backup_file.backup")`

## 🌟 Advanced Features

### Custom Template Directory
```python
cg = ConfigGenerator(template_dir="/custom/templates")
```

### Custom Output Directory
```python
cg = ConfigGenerator(output_dir="./configs")
```

### Disable Validation
```python
cg = ConfigGenerator(validate_configs=False)
```

### Disable Backups
```python
cg = ConfigGenerator(create_backups=False)
```

## 📝 API Reference

### ConfigGenerator Class

**Methods:**
- `generate(config_type, output_path=None, dry_run=False, **kwargs)` - Generate config
- `list_templates()` - List available templates
- `get_template_info(config_type)` - Get template details
- `list_backups()` - List all backups
- `restore_backup(config_type, backup_file, output_path=None)` - Restore from backup

**Attributes:**
- `template_dir` - Templates directory path
- `output_dir` - Output directory path
- `backup_dir` - Backups directory path
- `validate_configs` - Validation enabled flag
- `create_backups` - Backup enabled flag

## 🤝 Contributing

The system is designed for easy extension:

1. Add template: Create `.template` file in `templates/`
2. Add validator: Create validator class in `validators.py`
3. Register: Add to `TEMPLATE_EXTENSIONS` and `VALIDATORS`
4. Test: Add tests in `test_config_generator.py`
5. Document: Update README with parameters

## 📜 License

Part of the Cortex Linux project.

## 🙏 Acknowledgments

Built for Cortex Linux - The AI-Native Operating System

---

## 🎯 Summary

This Configuration File Template System provides a production-ready, well-tested, and thoroughly documented solution for generating configuration files. It exceeds all acceptance criteria with:

- ✅ **5 config types** (requirement: 4+)
- ✅ **Valid output** with comprehensive validation
- ✅ **28 tests** with 100% pass rate
- ✅ **Complete documentation** with examples

The code follows clean code principles, is cross-platform compatible, and includes features like automatic backups, dry-run mode, and extensive error handling.


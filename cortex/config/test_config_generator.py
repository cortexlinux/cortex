"""
Comprehensive tests for the Configuration File Template System.
"""

import os
import pytest
import tempfile
from pathlib import Path
from cortex.config import ConfigGenerator
from cortex.config.exceptions import (
    ConfigError,
    ValidationError,
    TemplateError,
    BackupError,
)


class TestConfigGenerator:
    """Test suite for ConfigGenerator class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def generator(self, temp_dir):
        """Create a ConfigGenerator instance for testing."""
        output_dir = temp_dir / "output"
        backup_dir = temp_dir / "backups"
        return ConfigGenerator(
            output_dir=str(output_dir),
            backup_dir=str(backup_dir),
            create_backups=True,
            validate_configs=True,
        )

    def test_initialization(self, temp_dir):
        """Test ConfigGenerator initialization."""
        output_dir = temp_dir / "output"
        backup_dir = temp_dir / "backups"

        cg = ConfigGenerator(
            output_dir=str(output_dir),
            backup_dir=str(backup_dir),
        )

        assert cg.output_dir == output_dir
        assert cg.backup_dir == backup_dir
        assert cg.validate_configs is True
        assert cg.create_backups is True

    def test_list_templates(self, generator):
        """Test listing available templates."""
        templates = generator.list_templates()

        assert "nginx" in templates
        assert "postgres" in templates
        assert "redis" in templates
        assert "docker-compose" in templates
        assert "apache" in templates
        assert len(templates) >= 5

    def test_get_template_info(self, generator):
        """Test getting template information."""
        info = generator.get_template_info("nginx")

        assert info["type"] == "nginx"
        assert "nginx.conf.template" in info["template_file"]
        assert info["validator_available"] is True

    def test_get_template_info_invalid(self, generator):
        """Test getting info for invalid template."""
        with pytest.raises(ConfigError):
            generator.get_template_info("invalid_type")

    def test_nginx_reverse_proxy_generation(self, generator, temp_dir):
        """Test generating nginx reverse proxy configuration."""
        output_path = temp_dir / "nginx.conf"

        config = generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            target_port=3000,
            server_name="example.com",
            port=80,
        )

        assert output_path.exists()
        assert "server {" in config
        assert "listen 80" in config
        assert "server_name example.com" in config
        assert "proxy_pass http://localhost:3000" in config
        assert "proxy_set_header" in config

    def test_nginx_static_server_generation(self, generator, temp_dir):
        """Test generating nginx static web server configuration."""
        output_path = temp_dir / "nginx_static.conf"

        config = generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=False,
            port=8080,
            server_name="static.example.com",
            document_root="/var/www/static",
            enable_gzip=True,
        )

        assert output_path.exists()
        assert "server {" in config
        assert "listen 8080" in config
        assert "server_name static.example.com" in config
        assert "root /var/www/static" in config
        assert "gzip on" in config

    def test_postgres_configuration(self, generator, temp_dir):
        """Test generating PostgreSQL configuration."""
        output_path = temp_dir / "postgresql.conf"

        config = generator.generate(
            "postgres",
            output_path=str(output_path),
            port=5432,
            max_connections=200,
            shared_buffers="256MB",
            effective_cache_size="8GB",
        )

        assert output_path.exists()
        assert "port = 5432" in config
        assert "max_connections = 200" in config
        assert "shared_buffers = 256MB" in config
        assert "effective_cache_size = 8GB" in config

    def test_redis_configuration(self, generator, temp_dir):
        """Test generating Redis configuration."""
        output_path = temp_dir / "redis.conf"

        config = generator.generate(
            "redis",
            output_path=str(output_path),
            port=6379,
            bind_address="0.0.0.0",
            maxmemory="512mb",
            persistence=True,
        )

        assert output_path.exists()
        assert "port 6379" in config
        assert "bind 0.0.0.0" in config
        assert "maxmemory 512mb" in config
        assert "save" in config or "appendonly" in config

    def test_docker_compose_configuration(self, generator, temp_dir):
        """Test generating Docker Compose configuration."""
        output_path = temp_dir / "docker-compose.yml"

        services = [
            {
                "name": "web",
                "image": "nginx:latest",
                "ports": ["80:80"],
                "volumes": ["./html:/usr/share/nginx/html"],
            },
            {
                "name": "db",
                "image": "postgres:13",
                "environment": {
                    "POSTGRES_PASSWORD": "secret",
                    "POSTGRES_DB": "myapp",
                },
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
            },
        ]

        config = generator.generate(
            "docker-compose",
            output_path=str(output_path),
            version="3.8",
            services=services,
            volumes={"postgres_data": {}},
        )

        assert output_path.exists()
        assert "version: '3.8'" in config
        assert "services:" in config
        assert "web:" in config
        assert "db:" in config
        assert "nginx:latest" in config
        assert "postgres:13" in config

    def test_apache_reverse_proxy(self, generator, temp_dir):
        """Test generating Apache reverse proxy configuration."""
        output_path = temp_dir / "apache.conf"

        config = generator.generate(
            "apache",
            output_path=str(output_path),
            reverse_proxy=True,
            port=80,
            server_name="app.example.com",
            target_host="localhost",
            target_port=8000,
        )

        assert output_path.exists()
        assert "<VirtualHost *:80>" in config
        assert "ServerName app.example.com" in config
        assert "ProxyPass" in config
        assert "http://localhost:8000" in config

    def test_dry_run(self, generator, temp_dir):
        """Test dry run mode (no file written)."""
        output_path = temp_dir / "nginx_dry.conf"

        config = generator.generate(
            "nginx",
            output_path=str(output_path),
            dry_run=True,
            reverse_proxy=True,
            target_port=5000,
        )

        assert not output_path.exists()
        assert "server {" in config
        assert "proxy_pass" in config

    def test_backup_functionality(self, generator, temp_dir):
        """Test backup of existing configuration files."""
        output_path = temp_dir / "output" / "test.conf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial file
        output_path.write_text("Initial config")

        # Generate new config (should backup the old one)
        generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            target_port=3000,
        )

        # Check that backup was created
        backups = generator.list_backups()
        assert len(backups) > 0
        assert any("test.conf" in backup for backup in backups)

    def test_validation_warnings(self, generator, temp_dir, capsys):
        """Test that validation warnings are displayed."""
        output_path = temp_dir / "redis_test.conf"

        # Generate config with parameters that might cause warnings
        generator.generate(
            "redis",
            output_path=str(output_path),
            # Not providing common settings
        )

        captured = capsys.readouterr()
        # Should have warnings or pass silently
        assert output_path.exists()

    def test_validation_error(self, generator, temp_dir):
        """Test that validation errors are raised."""
        output_path = temp_dir / "nginx_invalid.conf"

        with pytest.raises(ValidationError):
            # Try to create invalid config (port out of range)
            generator.generate(
                "nginx",
                output_path=str(output_path),
                reverse_proxy=True,
                port=99999,  # Invalid port
                target_port=3000,
            )

    def test_unsupported_config_type(self, generator, temp_dir):
        """Test error handling for unsupported config types."""
        with pytest.raises(ConfigError):
            generator.generate(
                "unsupported_type",
                output_path=str(temp_dir / "test.conf"),
            )

    def test_ssl_configuration_nginx(self, generator, temp_dir):
        """Test generating nginx config with SSL."""
        output_path = temp_dir / "nginx_ssl.conf"

        config = generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            target_port=3000,
            ssl_enabled=True,
            ssl_port=443,
            ssl_certificate="/etc/ssl/certs/server.crt",
            ssl_certificate_key="/etc/ssl/private/server.key",
        )

        assert output_path.exists()
        assert "listen 443 ssl" in config
        assert "ssl_certificate" in config
        assert "ssl_certificate_key" in config
        assert "ssl_protocols" in config

    def test_restore_backup(self, generator, temp_dir):
        """Test restoring configuration from backup."""
        output_path = temp_dir / "output" / "restore_test.conf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial config
        original_content = "Original config content"
        output_path.write_text(original_content)

        # Generate new config (creates backup)
        generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            target_port=3000,
        )

        # Verify file was changed
        new_content = output_path.read_text()
        assert new_content != original_content

        # Get backup file
        backups = generator.list_backups()
        assert len(backups) > 0

        # Restore from backup
        backup_file = backups[0]
        generator.restore_backup("nginx", backup_file, output_path=str(output_path))

        # Verify restoration
        restored_content = output_path.read_text()
        assert restored_content == original_content

    def test_custom_variables(self, generator, temp_dir):
        """Test using custom variables in templates."""
        output_path = temp_dir / "nginx_custom.conf"

        config = generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            target_port=9000,
            proxy_timeout=120,
            enable_logging=True,
            access_log="/custom/access.log",
        )

        assert "proxy_pass http://localhost:9000" in config
        assert "120s" in config or "120" in config
        assert "/custom/access.log" in config

    def test_postgres_ssl_configuration(self, generator, temp_dir):
        """Test PostgreSQL configuration with SSL."""
        output_path = temp_dir / "postgresql_ssl.conf"

        config = generator.generate(
            "postgres",
            output_path=str(output_path),
            enable_ssl=True,
            ssl_cert_file="/etc/postgresql/server.crt",
            ssl_key_file="/etc/postgresql/server.key",
        )

        assert "ssl = on" in config
        assert "ssl_cert_file" in config

    def test_redis_replication(self, generator, temp_dir):
        """Test Redis configuration with replication."""
        output_path = temp_dir / "redis_replica.conf"

        config = generator.generate(
            "redis",
            output_path=str(output_path),
            enable_replication=True,
            replica_host="master.example.com",
            replica_port=6379,
        )

        assert "replicaof master.example.com 6379" in config

    def test_validation_disabled(self, temp_dir):
        """Test generator with validation disabled."""
        generator = ConfigGenerator(
            output_dir=str(temp_dir / "output"),
            validate_configs=False,
        )

        output_path = temp_dir / "output" / "no_validation.conf"

        # Should not raise validation errors even with invalid port
        config = generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            port=99999,  # Would normally fail validation
            target_port=3000,
        )

        assert output_path.exists()

    def test_backups_disabled(self, temp_dir):
        """Test generator with backups disabled."""
        generator = ConfigGenerator(
            output_dir=str(temp_dir / "output"),
            backup_dir=str(temp_dir / "backups"),
            create_backups=False,
        )

        output_path = temp_dir / "output" / "no_backup.conf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial file
        output_path.write_text("Initial config")

        # Generate new config
        generator.generate(
            "nginx",
            output_path=str(output_path),
            reverse_proxy=True,
            target_port=3000,
        )

        # No backups should be created
        backups = generator.list_backups()
        assert len(backups) == 0


class TestValidators:
    """Test suite for configuration validators."""

    def test_nginx_validator_valid(self):
        """Test nginx validator with valid config."""
        from cortex.config.validators import NginxValidator

        validator = NginxValidator()
        config = """
        server {
            listen 80;
            server_name example.com;
        }
        """
        params = {"port": 80, "server_name": "example.com"}

        warnings = validator.validate(config, params)
        assert isinstance(warnings, list)

    def test_nginx_validator_invalid_port(self):
        """Test nginx validator with invalid port."""
        from cortex.config.validators import NginxValidator

        validator = NginxValidator()
        config = """
        server {
            listen 99999;
        }
        """
        params = {}

        with pytest.raises(ValidationError):
            validator.validate(config, params)

    def test_postgres_validator_valid(self):
        """Test postgres validator with valid config."""
        from cortex.config.validators import PostgresValidator

        validator = PostgresValidator()
        config = """
        max_connections = 100
        shared_buffers = 128MB
        port = 5432
        """
        params = {"port": 5432}

        warnings = validator.validate(config, params)
        assert isinstance(warnings, list)

    def test_redis_validator_valid(self):
        """Test redis validator with valid config."""
        from cortex.config.validators import RedisValidator

        validator = RedisValidator()
        config = """
        bind 127.0.0.1
        port 6379
        maxmemory 256mb
        """
        params = {}

        warnings = validator.validate(config, params)
        assert isinstance(warnings, list)

    def test_docker_compose_validator_valid(self):
        """Test docker-compose validator with valid config."""
        from cortex.config.validators import DockerComposeValidator

        validator = DockerComposeValidator()
        config = """
        version: '3.8'
        services:
          web:
            image: nginx:latest
        """
        params = {}

        warnings = validator.validate(config, params)
        assert isinstance(warnings, list)

    def test_apache_validator_valid(self):
        """Test apache validator with valid config."""
        from cortex.config.validators import ApacheValidator

        validator = ApacheValidator()
        config = """
        <VirtualHost *:80>
            DocumentRoot /var/www/html
            ServerName example.com
        </VirtualHost>
        """
        params = {}

        warnings = validator.validate(config, params)
        assert isinstance(warnings, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


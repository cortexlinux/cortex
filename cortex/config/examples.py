"""
Examples demonstrating the Configuration File Template System.

Run this file to see various configuration generation examples.
"""

from cortex.config import ConfigGenerator


def example_nginx_reverse_proxy():
    """Example: Generate nginx reverse proxy configuration."""
    print("=" * 60)
    print("Example 1: Nginx Reverse Proxy")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "nginx",
        output_path="./examples_output/nginx_proxy.conf",
        reverse_proxy=True,
        target_port=3000,
        server_name="app.example.com",
        port=80,
        enable_logging=True,
        proxy_timeout=60,
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_nginx_ssl():
    """Example: Generate nginx configuration with SSL."""
    print("=" * 60)
    print("Example 2: Nginx with SSL")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "nginx",
        output_path="./examples_output/nginx_ssl.conf",
        reverse_proxy=True,
        target_port=3000,
        server_name="secure.example.com",
        port=80,
        ssl_enabled=True,
        ssl_port=443,
        ssl_certificate="/etc/ssl/certs/server.crt",
        ssl_certificate_key="/etc/ssl/private/server.key",
        enable_logging=True,
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_postgres():
    """Example: Generate PostgreSQL configuration."""
    print("=" * 60)
    print("Example 3: PostgreSQL Database")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "postgres",
        output_path="./examples_output/postgresql.conf",
        port=5432,
        max_connections=200,
        shared_buffers="256MB",
        effective_cache_size="8GB",
        work_mem="8MB",
        maintenance_work_mem="128MB",
        log_slow_queries=True,
        slow_query_threshold=1000,
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_redis():
    """Example: Generate Redis configuration."""
    print("=" * 60)
    print("Example 4: Redis Cache Server")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "redis",
        output_path="./examples_output/redis.conf",
        port=6379,
        bind_address="127.0.0.1",
        maxmemory="512mb",
        maxmemory_policy="allkeys-lru",
        persistence=True,
        appendonly="yes",
        enable_protected_mode=True,
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_docker_compose_simple():
    """Example: Generate simple Docker Compose configuration."""
    print("=" * 60)
    print("Example 5: Docker Compose - Web + Database")
    print("=" * 60)

    cg = ConfigGenerator()

    services = [
        {
            "name": "web",
            "image": "nginx:latest",
            "ports": ["80:80"],
            "volumes": ["./html:/usr/share/nginx/html"],
            "depends_on": ["db"],
            "restart": "always",
        },
        {
            "name": "db",
            "image": "postgres:13",
            "environment": {
                "POSTGRES_PASSWORD": "mysecretpassword",
                "POSTGRES_DB": "myapp",
            },
            "volumes": ["postgres_data:/var/lib/postgresql/data"],
            "restart": "always",
        },
    ]

    config = cg.generate(
        "docker-compose",
        output_path="./examples_output/docker-compose.yml",
        version="3.8",
        services=services,
        volumes={"postgres_data": {}},
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_docker_compose_microservices():
    """Example: Generate Docker Compose for microservices."""
    print("=" * 60)
    print("Example 6: Docker Compose - Microservices")
    print("=" * 60)

    cg = ConfigGenerator()

    services = [
        {
            "name": "api",
            "build": {"context": "./api", "dockerfile": "Dockerfile"},
            "container_name": "app_api",
            "ports": ["3000:3000"],
            "environment": {
                "NODE_ENV": "production",
                "DATABASE_URL": "postgresql://db:5432/myapp",
                "REDIS_URL": "redis://redis:6379",
            },
            "depends_on": ["db", "redis"],
            "networks": ["backend"],
            "restart": "unless-stopped",
        },
        {
            "name": "frontend",
            "build": {"context": "./frontend"},
            "container_name": "app_frontend",
            "ports": ["8080:80"],
            "depends_on": ["api"],
            "networks": ["frontend", "backend"],
            "restart": "unless-stopped",
        },
        {
            "name": "db",
            "image": "postgres:13-alpine",
            "container_name": "app_db",
            "environment": {
                "POSTGRES_PASSWORD": "secret",
                "POSTGRES_DB": "myapp",
            },
            "volumes": ["postgres_data:/var/lib/postgresql/data"],
            "networks": ["backend"],
            "restart": "unless-stopped",
        },
        {
            "name": "redis",
            "image": "redis:alpine",
            "container_name": "app_redis",
            "volumes": ["redis_data:/data"],
            "networks": ["backend"],
            "restart": "unless-stopped",
        },
    ]

    config = cg.generate(
        "docker-compose",
        output_path="./examples_output/docker-compose-microservices.yml",
        version="3.8",
        services=services,
        networks={
            "frontend": {"driver": "bridge"},
            "backend": {"driver": "bridge"},
        },
        volumes={
            "postgres_data": {},
            "redis_data": {},
        },
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_apache_reverse_proxy():
    """Example: Generate Apache reverse proxy configuration."""
    print("=" * 60)
    print("Example 7: Apache Reverse Proxy")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "apache",
        output_path="./examples_output/apache_proxy.conf",
        reverse_proxy=True,
        port=80,
        server_name="app.example.com",
        server_alias="www.app.example.com",
        target_host="localhost",
        target_port=8000,
        enable_logging=True,
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_dry_run():
    """Example: Use dry run mode to preview configuration."""
    print("=" * 60)
    print("Example 8: Dry Run Mode (Preview Only)")
    print("=" * 60)

    cg = ConfigGenerator()

    # Generate without writing to file
    config = cg.generate(
        "nginx",
        dry_run=True,
        reverse_proxy=True,
        target_port=5000,
        server_name="preview.example.com",
    )

    print("\nPreview (not written to file):")
    print(config)
    print()


def example_list_templates():
    """Example: List available templates."""
    print("=" * 60)
    print("Example 9: List Available Templates")
    print("=" * 60)

    cg = ConfigGenerator()

    templates = cg.list_templates()
    print("\nAvailable Templates:")
    for template in templates:
        info = cg.get_template_info(template)
        print(f"\n  {template}:")
        print(f"    Template File: {info['template_file']}")
        print(f"    Default Path: {info['default_path']}")
        print(f"    Validation: {'Yes' if info['validator_available'] else 'No'}")
    print()


def example_backup_and_restore():
    """Example: Demonstrate backup and restore functionality."""
    print("=" * 60)
    print("Example 10: Backup and Restore")
    print("=" * 60)

    cg = ConfigGenerator()

    # Create initial config
    print("Creating initial configuration...")
    cg.generate(
        "nginx",
        output_path="./examples_output/backup_test.conf",
        reverse_proxy=True,
        target_port=3000,
    )

    # Generate new config (will backup the old one)
    print("\nUpdating configuration (old one will be backed up)...")
    cg.generate(
        "nginx",
        output_path="./examples_output/backup_test.conf",
        reverse_proxy=True,
        target_port=4000,  # Different port
    )

    # List backups
    print("\nAvailable Backups:")
    backups = cg.list_backups()
    for backup in backups:
        print(f"  - {backup}")

    print()


def example_postgres_replication():
    """Example: PostgreSQL with replication enabled."""
    print("=" * 60)
    print("Example 11: PostgreSQL with Replication")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "postgres",
        output_path="./examples_output/postgresql_replica.conf",
        port=5432,
        max_connections=100,
        shared_buffers="128MB",
        enable_replication=True,
        max_wal_senders=10,
        wal_keep_size="1GB",
        hot_standby="on",
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def example_redis_replication():
    """Example: Redis with replication enabled."""
    print("=" * 60)
    print("Example 12: Redis Replication")
    print("=" * 60)

    cg = ConfigGenerator()

    config = cg.generate(
        "redis",
        output_path="./examples_output/redis_replica.conf",
        port=6379,
        bind_address="0.0.0.0",
        maxmemory="1gb",
        enable_replication=True,
        replica_host="master.example.com",
        replica_port=6379,
    )

    print("\nGenerated Configuration:")
    print(config)
    print()


def main():
    """Run all examples."""
    import os

    # Create output directory
    os.makedirs("examples_output", exist_ok=True)

    print("\n" + "=" * 60)
    print("CORTEX CONFIGURATION GENERATOR - EXAMPLES")
    print("=" * 60 + "\n")

    # Run examples
    example_nginx_reverse_proxy()
    example_nginx_ssl()
    example_postgres()
    example_redis()
    example_docker_compose_simple()
    example_docker_compose_microservices()
    example_apache_reverse_proxy()
    example_dry_run()
    example_list_templates()
    example_backup_and_restore()
    example_postgres_replication()
    example_redis_replication()

    print("=" * 60)
    print("All examples completed!")
    print("Generated files are in: ./examples_output/")
    print("=" * 60)


if __name__ == "__main__":
    main()


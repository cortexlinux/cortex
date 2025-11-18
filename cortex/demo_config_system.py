#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Demo of the Configuration File Template System

This script demonstrates the key features of the system.
"""

import sys
import io
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ConfigGenerator

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def demo():
    """Run a quick demonstration of the config system."""
    
    print("\n" + "="*70)
    print("CORTEX CONFIGURATION FILE TEMPLATE SYSTEM - DEMO")
    print("="*70 + "\n")

    print("[*] Initializing ConfigGenerator...")
    cg = ConfigGenerator(output_dir="./demo_output")
    print("[+] ConfigGenerator initialized!\n")

    print("[*] Available Configuration Types:")
    templates = cg.list_templates()
    for i, template in enumerate(templates, 1):
        info = cg.get_template_info(template)
        print(f"  {i}. {template.upper()}")
        print(f"     Template: {info['template_file']}")
    print()

    # Demo 1: Nginx Reverse Proxy
    print("[*] Demo 1: Generating Nginx Reverse Proxy Configuration")
    print("-" * 70)
    nginx_config = cg.generate(
        "nginx",
        output_path="./demo_output/nginx.conf",
        reverse_proxy=True,
        target_port=3000,
        server_name="app.example.com",
        port=80,
        enable_logging=True
    )
    print(f"[+] Generated {len(nginx_config)} characters of configuration\n")

    # Demo 2: PostgreSQL
    print("[*] Demo 2: Generating PostgreSQL Configuration")
    print("-" * 70)
    postgres_config = cg.generate(
        "postgres",
        output_path="./demo_output/postgresql.conf",
        port=5432,
        max_connections=100,
        shared_buffers="128MB",
        effective_cache_size="4GB"
    )
    print(f"[+] Generated {len(postgres_config)} characters of configuration\n")

    # Demo 3: Docker Compose
    print("[*] Demo 3: Generating Docker Compose Configuration")
    print("-" * 70)
    services = [
        {
            "name": "web",
            "image": "nginx:latest",
            "ports": ["80:80"],
            "restart": "always"
        },
        {
            "name": "db",
            "image": "postgres:13",
            "environment": {
                "POSTGRES_PASSWORD": "secret",
                "POSTGRES_DB": "myapp"
            },
            "restart": "always"
        }
    ]
    
    docker_config = cg.generate(
        "docker-compose",
        output_path="./demo_output/docker-compose.yml",
        version="3.8",
        services=services
    )
    print(f"[+] Generated {len(docker_config)} characters of configuration\n")

    # Demo 4: Dry Run
    print("[*] Demo 4: Dry Run Mode (Preview Only)")
    print("-" * 70)
    preview = cg.generate(
        "redis",
        dry_run=True,
        port=6379,
        maxmemory="512mb",
        persistence=True
    )
    print("Preview (first 300 characters):")
    print(preview[:300] + "...\n")

    # Demo 5: List Backups
    print("[*] Demo 5: Backup System")
    print("-" * 70)
    backups = cg.list_backups()
    if backups:
        print(f"[+] Found {len(backups)} backup(s):")
        for backup in backups[:3]:
            print(f"  - {backup}")
    else:
        print("[i] No backups yet (backups are created when overwriting existing files)")
    print()

    # Summary
    print("="*70)
    print("[SUCCESS] DEMO COMPLETED SUCCESSFULLY!")
    print("="*70)
    print("\n[*] Generated files are in: ./demo_output/")
    print("\n[*] For more examples, run: python cortex/config/examples.py")
    print("[*] To run tests: pytest cortex/config/test_config_generator.py -v")
    print("\n[*] Full documentation: cortex/config/README.md")
    print("[*] Project summary: cortex/docs/CONFIGURATION_SYSTEM.md\n")


if __name__ == "__main__":
    try:
        demo()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


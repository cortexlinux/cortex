"""
Template Manager for Cortex Linux
Handles lifecycle of system duplication templates.
"""

import json
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from cortex.config_manager import ConfigManager


class TemplateManager:
    """
    Manages system templates for duplication and deployment.

    Templates are stored in ~/.cortex/templates/
    Structure:
    ~/.cortex/templates/
        name/
            v1/
                template.yaml
                metadata.json
            v2/
                ...
    """

    def __init__(self, template_dir: Path | None = None):
        self.base_dir = template_dir or Path.home() / ".cortex" / "templates"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config_manager = ConfigManager()

    def create_template(
        self, name: str, description: str, package_sources: list[str] | None = None
    ) -> str:
        """
        Create a new system template.
        """
        template_dir = self.base_dir / name
        template_dir.mkdir(parents=True, exist_ok=True)

        # Get next version
        def get_v_num(v_str):
            match = re.search(r"v(\d+)", v_str)
            return int(match.group(1)) if match else 0

        versions = [
            get_v_num(d.name)
            for d in template_dir.iterdir()
            if d.is_dir() and d.name.startswith("v")
        ]
        next_v = max(versions) + 1 if versions else 1

        version_name = f"v{next_v}"
        version_dir = template_dir / version_name
        version_dir.mkdir()

        config_file = version_dir / "template.yaml"
        metadata_file = version_dir / "metadata.json"

        # Capture system state
        self.config_manager.export_configuration(str(config_file), package_sources=package_sources)

        # Save metadata
        metadata = {
            "name": name,
            "version": version_name,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "cortex_version": self.config_manager.CORTEX_VERSION,
        }
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        return version_name

    def list_templates(self) -> list[dict[str, Any]]:
        """
        List all available templates and their versions.
        """
        templates = []
        if not self.base_dir.exists():
            return []

        for template_dir in self.base_dir.iterdir():
            if not template_dir.is_dir():
                continue

            versions = []
            for v_dir in template_dir.iterdir():
                if not v_dir.is_dir() or not v_dir.name.startswith("v"):
                    continue

                metadata_file = v_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file) as f:
                        versions.append(json.load(f))

            if versions:
                # Sort versions by version number descending
                def get_v_num(v_str):
                    match = re.search(r"v(\d+)", v_str)
                    return int(match.group(1)) if match else 0

                versions.sort(key=lambda x: get_v_num(x["version"]), reverse=True)
                templates.append(
                    {
                        "name": template_dir.name,
                        "latest_version": versions[0]["version"],
                        "versions": versions,
                    }
                )

        return sorted(templates, key=lambda x: x["name"])

    def get_template(self, name: str, version: str | None = None) -> dict[str, Any] | None:
        """
        Retrieve a specific template version.
        """
        template_path = self.base_dir / name
        if not template_path.exists():
            return None

        if not version:
            # Use latest version
            def get_v_num(v_str):
                match = re.search(r"v(\d+)", v_str)
                return int(match.group(1)) if match else 0

            versions = [
                v.name for v in template_path.iterdir() if v.is_dir() and v.name.startswith("v")
            ]
            if not versions:
                return None
            version = sorted(versions, key=get_v_num)[-1]

        version_path = template_path / version
        if not version_path.exists():
            return None

        metadata_file = version_path / "metadata.json"
        config_file = version_path / "template.yaml"

        if not metadata_file.exists() or not config_file.exists():
            return None

        with open(metadata_file) as f:
            data = json.load(f)

        with open(config_file) as f:
            data["config"] = yaml.safe_load(f)

        return data

    def delete_template(self, name: str, version: str | None = None) -> bool:
        """
        Delete a template or a specific version.
        """
        template_path = self.base_dir / name
        if not template_path.exists():
            return False

        if version:
            version_path = template_path / version
            if version_path.exists():
                shutil.rmtree(version_path)
                # If no versions left, remove the template folder
                if not any(template_path.iterdir()):
                    shutil.rmtree(template_path)
                return True
            return False
        else:
            shutil.rmtree(template_path)
            return True

    def export_template(self, name: str, version: str, output_path: str) -> str:
        """
        Export a template version as a ZIP file.
        """
        template_data = self.base_dir / name / version
        if not template_data.exists():
            raise ValueError(f"Template {name}:{version} not found")

        output_path = Path(output_path)
        if output_path.suffix != ".zip":
            output_path = output_path.with_suffix(".zip")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(template_data):
                for file in files:
                    file_path = Path(root) / file
                    zipf.write(file_path, file_path.relative_to(template_data))

        return str(output_path)

    def import_template(self, input_path: str) -> tuple[str, str]:
        """
        Import a template from a ZIP file.
        """
        input_path = Path(input_path).resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        # Extract to temporary location to read metadata
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()
            with zipfile.ZipFile(input_path, "r") as zipf:
                for member in zipf.infolist():
                    # Zip Slip protection: check for absolute paths or ".."
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member.filename:
                        continue  # Skip unsafe members

                    target = (tmpdir_path / member_path).resolve()
                    if not target.is_relative_to(tmpdir_path):
                        continue  # Skip members outside tmpdir

                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zipf.open(member) as source, open(target, "wb") as dest:
                            shutil.copyfileobj(source, dest)

            metadata_file = tmpdir_path / "metadata.json"
            if not metadata_file.exists():
                raise ValueError("Invalid template: missing metadata.json")

            with open(metadata_file) as f:
                metadata = json.load(f)

            raw_name = metadata.get("name", "")
            raw_version = metadata.get("version", "")

            # Sanitize name and version to prevent path traversal
            if not re.match(r"^[a-zA-Z0-9._-]+$", raw_name) or not re.match(
                r"^[a-zA-Z0-9._-]+$", raw_version
            ):
                raise ValueError("Invalid template: malformed name or version")

            name = raw_name
            version = raw_version

            # Ensure target path is strictly within base_dir
            target_path = (self.base_dir / name / version).resolve()
            if not target_path.is_relative_to(self.base_dir.resolve()):
                raise ValueError("Invalid template: target path outside templates directory")

            if target_path.exists():
                # Append import suffix if version already exists
                import time

                version = f"{version}-import-{int(time.time())}"
                target_path = self.base_dir / name / version

            target_path.mkdir(parents=True, exist_ok=True)
            for item in tmpdir_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, target_path / item.name)

            return name, version

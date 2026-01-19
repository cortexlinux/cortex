import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from cortex.config_manager import ConfigManager
from cortex.hardware_detection import detect_hardware
from cortex.installation_history import InstallationHistory, InstallationStatus

# Optional dependencies for documentation export
try:
    import markdown
except ImportError:
    markdown = None

try:
    import pdfkit
except ImportError:
    pdfkit = None

logger = logging.getLogger(__name__)


class DocsGenerator:
    """Core engine for generating system and software documentation."""

    def __init__(self) -> None:
        """Initialize docs generator, configure paths and helpers."""
        self.config_manager = ConfigManager()
        self.history = InstallationHistory()
        self.console = Console()
        self.docs_dir = (Path.home() / ".cortex" / "docs").resolve()
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.template_base_dir = (Path(__file__).parent / "templates" / "docs").resolve()

    def _sanitize_name(self, software_name: str) -> str:
        """Sanitize and validate software name to prevent path traversal."""
        if not software_name:
            raise ValueError("Software name cannot be empty")

        # Allow only alphanumeric, dots, underscores, pluses, and hyphens.
        # Replace everything else with underscores.
        safe = re.sub(r"[^A-Za-z0-9._+-]", "_", software_name).strip("._")

        if not safe:
            raise ValueError(f"Invalid characters in software name: {software_name}")

        return safe

    def _get_software_dir(self, software_name: str) -> Path:
        """Get and validate software directory."""
        safe_name = self._sanitize_name(software_name)
        software_dir = (self.docs_dir / safe_name).resolve()

        if self.docs_dir not in software_dir.parents:
            raise ValueError(f"Invalid software name (path escape attempt): {software_name}")

        return software_dir

    def _get_system_data(self) -> dict[str, Any]:
        """Gather comprehensive system data."""
        hw_info = detect_hardware()
        packages = self.config_manager.detect_installed_packages()

        return {
            "system": hw_info.to_dict(),
            "packages": packages,
            "generated_at": datetime.now().isoformat(),
        }

    def _get_software_data(self, software_name: str) -> dict[str, Any]:
        """Gather documentation data for a specific software/package."""
        safe_name = self._sanitize_name(software_name)
        # Find package in installed packages
        all_packages = self.config_manager.detect_installed_packages()
        pkg_info = next((p for p in all_packages if p["name"] == safe_name), None)

        # Get installation history for this package
        history_records = self.history.get_history(limit=100)
        pkg_history = [
            r
            for r in history_records
            if software_name in r.packages and r.status == InstallationStatus.SUCCESS
        ]

        # Latest successful installation
        latest_install = pkg_history[0] if pkg_history else None

        # Attempt to find config files (from snapshots if available)
        config_files = []
        if latest_install and latest_install.after_snapshot:
            for snap in latest_install.after_snapshot:
                if snap.package_name == software_name:
                    config_files = snap.config_files
                    break

        # If no snapshots, try searching standard locations
        if not config_files:
            config_files = self._find_config_files(software_name)

        return {
            "name": software_name,
            "package_info": pkg_info,
            "latest_install": latest_install,
            "history": pkg_history,
            "config_files": config_files,
            "generated_at": datetime.now().isoformat(),
        }

    def _find_config_files(self, software_name: str) -> list[str]:
        """Search for configuration files in standard locations."""
        safe_name = self._sanitize_name(software_name)
        potential_paths = [
            f"/etc/{safe_name}",
            f"/etc/{safe_name}.conf",
            f"/etc/{safe_name}/{safe_name}.conf",
            f"/etc/{safe_name}rc",
            os.path.expanduser(f"~/.{safe_name}rc"),
            os.path.expanduser(f"~/.config/{safe_name}"),
        ]

        found = []
        for path in potential_paths:
            if os.path.exists(path):
                found.append(path)

        # Also try listing /etc/software_name/ if it's a directory
        etc_dir = Path(f"/etc/{safe_name}")
        if etc_dir.is_dir():
            try:
                for item in etc_dir.glob("*"):
                    if item.is_file() and item.suffix in (
                        ".conf",
                        ".yaml",
                        ".yml",
                        ".json",
                        ".ini",
                    ):
                        found.append(str(item))
            except (PermissionError, OSError) as e:
                logger.warning(f"Error scanning {etc_dir} for config files: {e}")

        return sorted(set(found))

    def generate_software_docs(self, software_name: str) -> dict[str, str]:
        """Generate multiple MD documents for a software."""
        software_dir = self._get_software_dir(software_name)
        data = self._get_software_data(software_name)

        docs = {
            "Installation_Guide.md": self._render_installation_guide(data),
            "Configuration_Reference.md": self._render_config_reference(data),
            "Quick_Start.md": self._render_quick_start(data),
            "Troubleshooting.md": self._render_troubleshooting(data),
        }

        # software_dir is already validated by _get_software_dir
        software_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in docs.items():
            with open(software_dir / filename, "w") as f:
                f.write(content)

        return {filename: str(software_dir / filename) for filename in docs}

    def _get_template(self, software_name: str, guide_name: str) -> Template:
        """Load a template for a specific software or the default."""
        safe_name = self._sanitize_name(software_name)
        software_template = (self.template_base_dir / safe_name / f"{guide_name}.md").resolve()
        default_template = (self.template_base_dir / "default" / f"{guide_name}.md").resolve()

        if self.template_base_dir not in software_template.parents:
            # Fallback to default if someone tries to escape via guide_name or if safe_name is weird
            # though safe_name is sanitized.
            template_path = default_template
        else:
            template_path = software_template if software_template.exists() else default_template

        try:
            with open(template_path) as f:
                return Template(f.read())
        except Exception as e:
            logger.error(f"Failed to load template {guide_name}: {e}")
            return Template("# ${name}\n\nDocumentation template missing.")

    def _render_installation_guide(self, data: dict[str, Any]) -> str:
        name = data["name"]
        pkg = data["package_info"]
        install = data["latest_install"]

        history_content = ""
        if install:
            history_content = (
                f"- **Installed On**: {install.timestamp}\n\n## Installation Commands\n\n```bash\n"
            )
            for cmd in install.commands_executed:
                history_content += f"{cmd}\n"
            history_content += "```\n"
        else:
            history_content = "\n> [!NOTE]\n> No installation history found in Cortex database.\n"
            history_content += (
                "> This software was likely installed manually or before Cortex was configured.\n"
            )

        template = self._get_template(name, "Installation_Guide")
        return template.safe_substitute(
            name=name,
            version=pkg.get("version", "Unknown") if pkg else "Unknown",
            source=pkg.get("source", "Unknown") if pkg else "Unknown",
            history_content=history_content,
        )

    def _render_config_reference(self, data: dict[str, Any]) -> str:
        name = data["name"]
        configs = data["config_files"]

        config_content = ""
        if configs:
            config_content = "Detected configuration files:\n\n"
            for cfg in configs:
                config_content += f"- `{cfg}`\n"
        else:
            config_content = "*No specific configuration files detected for this package.*\n"

        template = self._get_template(name, "Configuration_Reference")
        return template.safe_substitute(name=name, config_content=config_content)

    def _render_quick_start(self, data: dict[str, Any]) -> str:
        name = data["name"]
        pkg = data["package_info"]

        quick_start_content = ""
        if pkg:
            quick_start_content = "## Common Commands\n\n"
            if pkg["source"] == "apt":
                quick_start_content += (
                    f"```bash\nsudo systemctl status {name}\nsudo systemctl start {name}\n```\n"
                )
            elif pkg["source"] == "pip":
                quick_start_content += f"```bash\npython3 -m {name} --help\n```\n"

        template = self._get_template(name, "Quick_Start")
        return template.safe_substitute(
            name=name, generated_at=data["generated_at"], quick_start_content=quick_start_content
        )

    def _render_troubleshooting(self, data: dict[str, Any]) -> str:
        name = data["name"]
        template = self._get_template(name, "Troubleshooting")
        return template.safe_substitute(name=name)

    def view_guide(self, software_name: str, guide_type: str) -> None:
        """View a documentation guide in the terminal."""
        software_dir = self._get_software_dir(software_name)
        guide_map = {
            "installation": "Installation_Guide.md",
            "config": "Configuration_Reference.md",
            "quick-start": "Quick_Start.md",
            "troubleshooting": "Troubleshooting.md",
        }

        filename = guide_map.get(guide_type.lower())
        if not filename:
            self.console.print(f"[red]Unknown guide type: {guide_type}[/red]")
            return

        filepath = software_dir / filename
        if not filepath.exists():
            # Try to generate it
            self.generate_software_docs(software_name)

        if filepath.exists():
            with open(filepath) as f:
                content = f.read()
            self.console.print(Markdown(content))
        else:
            self.console.print(f"[red]Documentation not found for {software_name}[/red]")

    def export_docs(self, software_name: str, format: str = "md") -> str:
        """Export documentation in various formats."""
        safe_name = self._sanitize_name(software_name)
        software_dir = self._get_software_dir(software_name)

        format = format.lower()
        if format not in ("md", "html", "pdf"):
            raise ValueError(f"Unsupported or invalid export format: {format}")

        if not software_dir.exists():
            self.generate_software_docs(software_name)

        export_path = Path.cwd() / f"{safe_name}_docs.{format}"

        if format == "md":
            # Combine all MD files
            combined = f"# {safe_name.capitalize()} Documentation\n\n"
            for filename in sorted(os.listdir(software_dir)):
                if filename.endswith(".md"):
                    with open(software_dir / filename) as f:
                        combined += f.read() + "\n\n---\n\n"

            with open(export_path, "w") as f:
                f.write(combined)

        elif format == "html":
            # Simple MD to HTML conversion
            if not markdown:
                return "Error: 'markdown' package is not installed. Use 'pip install cortex-linux[export]'."

            combined = ""
            for filename in sorted(os.listdir(software_dir)):
                if filename.endswith(".md"):
                    with open(software_dir / filename) as f:
                        combined += f.read() + "\n\n"

            html = markdown.markdown(combined)
            wrap = f"<html><body>{html}</body></html>"
            with open(export_path, "w") as f:
                f.write(wrap)

        elif format == "pdf":
            if not pdfkit:
                html_path = self.export_docs(software_name, "html")
                return f"PDF export failed (missing pdfkit). Exported to HTML instead: {html_path}"

            try:
                html_path = self.export_docs(software_name, "html")
                pdfkit.from_file(html_path, str(export_path))
                os.remove(html_path)
            except Exception as e:
                # Fallback for runtime error during PDF conversion
                html_path = str(Path.cwd() / f"{software_name}_docs.html")
                if not Path(html_path).exists():
                    self.export_docs(software_name, "html")
                return f"PDF export failed ({e}). HTML file was created at: {html_path}"

        return str(export_path)

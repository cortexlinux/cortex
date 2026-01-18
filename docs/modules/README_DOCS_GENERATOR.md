# Documentation Generator Module

The `DocsGenerator` module is responsible for automatically creating, managing, and exporting documentation for software packages and system configurations.

## Overview

Cortex provides a comprehensive documentation system that goes beyond simple logs. It uses data gathered during installations, configuration snapshots, and proactive system searches to build useful documentation files.

## Features

- **Automated Generation**: Documentation is automatically updated when software is successfully installed or modified via Cortex.
- **Rich Terminal View**: View documentation directly in your terminal with beautiful formatting and syntax highlighting.
- **Multiple Export Formats**: Export unified documentation files in Markdown, HTML, or PDF formats.
- **Customizable Templates**: Customize the layout and content of generated documentation using external templates.
- **Proactive Intelligence**: Attempts to locate configuration files and system paths even if the software wasn't installed via Cortex.

## Architecture

The module consists of the following components:

- **DocsGenerator (`cortex/docs_generator.py`)**: The core engine that orchestrates data gathering, rendering, and file management.
- **Templates (`cortex/templates/docs/`)**: Markdown templates used for different guide types (Installation, Configuration, Quick Start, Troubleshooting).
- **CLI Interface (`cortex/cli.py`)**: The `cortex docs` command group.

## Usage

### CLI Commands

```bash
# Generate documentation for a package
cortex docs generate <software_name>

# View a specific guide in the terminal
cortex docs view <software_name> <guide_type>
# Guide types: installation, config, quick-start, troubleshooting

# Export documentation to a file
cortex docs export <software_name> --format <md|html|pdf>
```

### Customization

You can provide custom templates for specific software by creating a directory in `cortex/templates/docs/${software_name}/`.

The generator looks for the following files:
- `Installation_Guide.md`
- `Configuration_Reference.md`
- `Quick_Start.md`
- `Troubleshooting.md`

If a software-specific template is missing, it falls back to the templates in `cortex/templates/docs/default/`.

### Exporting to PDF

Native PDF export requires the `wkhtmltopdf` system utility to be installed on your machine.

If it's missing, Cortex will automatically fall back to an HTML export and provide an informational message.

To enable PDF support, install it via your package manager:
```bash
sudo apt install wkhtmltopdf
```

## Data Sources

The generator gathers data from:
1.  **InstallationHistory**: Successful commands and timestamps.
2.  **ConfigManager**: System package information and configuration snapshots.
3.  **HardwareDetector**: System-wide hardware context.
4.  **Proactive Scanner**: Searches `/etc/`, `~/.config/`, and other standard locations for configuration files.

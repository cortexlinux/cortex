# Changelog Command

The `changelog` command allows users to view package changelogs and release notes directly from the Cortex CLI.

This feature helps users quickly understand what has changed between package versions, including security fixes, bug fixes, and new features.

---

## Usage

```bash
python -m cortex.cli changelog <package>
```

---

## Example

```bash
python -m cortex.cli changelog docker
```

---

## Sample Output

```text
24.0.7 (2023-11-15)
   🔐 Security: CVE-2023-12345 fixed
   🐛 Bug fixes: Container restart issues
   ✨ New: BuildKit 0.12 support

24.0.6 (2023-10-20)
   🐛 Bug fixes: Network reliability improvements
```

---

## Features

- Displays changelogs grouped by version
- Highlights:
  - 🔐 Security fixes
  - 🐛 Bug fixes
  - ✨ New features
- Works without LLM or external API dependencies

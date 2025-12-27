# Stdin (Pipe) Support

Cortex supports Unix-style stdin piping, allowing it to consume input from other commands.

This enables powerful workflows such as analyzing logs, diffs, or generated text directly.

## Basic Usage

You can pipe input into Cortex using standard shell syntax:

```bash
cat file.txt | cortex install docker --dry-run
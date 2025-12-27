# Natural Language Parser (NL Parser)

## Overview
The NL Parser enables users to describe installation requests in natural language
(e.g., “install docker and kubernetes” or “set up python dev environment”).
It converts free-form text into structured intents that Cortex can act upon.

This improves demo reliability and usability by removing the need for strict
command syntax.

---

## Key Features
- Typo tolerance (e.g., kubernets → kubernetes, pyhton → python)
- Rule-based + fuzzy semantic intent detection
- Confidence scoring for detected intent
- Clarification prompts for ambiguous requests
- Slot extraction (python version, platform, packages)
- Lightweight, dependency-free core logic

---

## Usage Example

```python
from cortex.nl_parser import parse_request

result = parse_request("pls install pyhton 3.10 on mac")

print(result)



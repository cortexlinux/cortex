# NLParser — Natural Language Install in Cortex

NLParser is the component that enables Cortex to understand and execute software installation requests written in **natural language**, while ensuring **safety, transparency, and user control**.

This document fully describes:
- the requirements asked in the issue
- what has been implemented
- how the functionality works end-to-end
- how each requirement is satisfied with this implementation

This file is intended to be **self-contained documentation**.

---

## Requirements from the Issue

The Natural Language Install feature was required to:

1. Support natural language install requests  
2. Handle ambiguous inputs gracefully  
3. Avoid hardcoded package or domain mappings  
4. Show reasoning / understanding to the user  
5. Be reliable for demos (stable behavior)  
6. Require explicit user confirmation before execution  
7. Allow users to edit or cancel planned commands  
8. Correctly understand common requests such as:
   - Python / Machine Learning
   - Kubernetes (`k8s`)
9. Prevent unsafe or guaranteed execution failures  
10. Be testable and deterministic where possible  

---

## What Has Been Implemented

NLParser implements a **multi-stage, human-in-the-loop workflow**:

- LLM-based intent extraction (no hardcoding)
- Explicit ambiguity handling
- Transparent command planning (preview-only by default)
- Explicit execution via `--execute`
- Interactive confirmation to execute the commands(`yes / edit / no`)
- Environment safety checks before execution
- Stable behavior despite LLM nondeterminism

---


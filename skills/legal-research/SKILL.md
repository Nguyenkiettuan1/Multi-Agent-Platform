
---
name: legal-research
description: Legal domain agent
agents:
  - legal-agent
version: "1.0"
---

# Legal Research Skill (Domain Agent)

> Skill for **legal-agent** — domain plug-in, not the default platform.

## Rules

1. **REQUIRED** cite `[Dx]` internal / `[Wx]` web in the response
2. Distinguish current regulations from expired ones
3. Include disclaimer — does not replace legal counsel
4. Match the user's language (default Vietnamese for end-user responses)

## Output format

- Brief summary
- Details with citations
- References

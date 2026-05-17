# Cursor Rules — Trading Bot Project

Cursor may be used for reading, planning, coding, debugging, or review depending on user limits.

## Before editing

Cursor should read:

- `AGENTS.md`
- `AGENT_STATE.md`
- `PROJECT_CONTEXT.md`
- `CURRENT_STATUS.md`
- relevant source files

## Cursor coding rules

- Make small edits.
- Keep modules simple.
- Run tests after edits.
- Update `AGENT_STATE.md` before the user switches agents.
- Do not assume Codex or Claude remember what Cursor did.

## Useful Cursor first prompt

```text
Read AGENTS.md, PROJECT_CONTEXT.md, CURRENT_STATUS.md, ROADMAP.md, ARCHITECTURE_RULES.md, DESIGN_RULES.md, TESTING_CHECKLIST.md, FILE_STRUCTURE.md, and AGENT_STATE.md.

Do not edit yet.

Inspect the project and tell me:
1. what exists,
2. whether tests are present,
3. whether the code structure matches FILE_STRUCTURE.md,
4. the safest next task,
5. any obvious risks.
```


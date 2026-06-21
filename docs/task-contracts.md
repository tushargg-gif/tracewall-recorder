# Task Contracts

A task contract describes what the agent is supposed to do and what it is allowed to touch.

Tracewall Recorder uses the contract during verification. Vague tasks produce weak evidence, so make the contract narrow when possible.

## Minimal Example

```yaml
task_id: AUTH-142
title: Fix expired JWT refresh bug

allowed_paths:
  - src/auth/**
  - tests/auth/**

forbidden_paths:
  - .env
  - infra/**
  - secrets/**

allowed_commands:
  - pytest tests/auth

success_criteria:
  - auth regression test added
  - auth tests pass
  - no unrelated files changed

verification:
  tests:
    - pytest tests/auth

risk_level: medium
human_approval_required: true
```

## Fields

`task_id`

A stable identifier for the task.

`title`

Human-readable task summary.

`allowed_paths`

Paths the agent is expected to modify.

`forbidden_paths`

Paths the agent should not modify.

`allowed_commands`

Commands that count as approved command evidence.

`success_criteria`

Plain-language expectations for the work.

`verification`

Verifier hints, such as required test commands.

## Guidance

- Keep allowed paths small.
- Include the exact tests the agent should run.
- Mark secrets, infra, deployment, and lock files as forbidden when appropriate.


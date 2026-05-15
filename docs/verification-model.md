# Verification Model

AgentProof Recorder verifies recorded evidence against the task contract.

It does not prove that code is correct. It checks whether the recorded run provides enough evidence to trust, review, block, or rerun the work.

## Inputs

- task contract
- git/file changes
- wrapped command events
- universal events
- MCP/tool events
- policy decisions
- final agent response
- event hash chain

## Checks

Current checks include:

- changed files recorded
- allowed and forbidden paths
- secret-like files
- dependency file changes
- allowed commands
- command exit codes
- missing tests
- large diffs
- expected data files
- expected artifacts
- network policy
- browser policy
- MCP policy
- event-chain integrity
- secret redaction

## Verdicts

`Pass`

The run has no failed checks and no policy violations.

`Partial Pass`

Some evidence is good, but warnings or incomplete evidence require human review.

`Fail`

The run has failed checks or critical policy violations.

## Scoring

The score is a local heuristic over dimensions such as:

- completion
- correctness
- containment
- safety
- reproducibility
- efficiency
- documentation

The score should be read as a review signal, not a benchmark of model intelligence.

## Event Integrity

Events are written to JSONL with hash chaining. This makes local evidence tamper-evident: changing an older event should break verification.

This is not tamper-proof storage. For higher assurance, future versions may add signing or remote notarization.


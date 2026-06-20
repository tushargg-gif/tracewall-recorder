from __future__ import annotations

from agentproof.events import (
    event_hash,
    mask_secret_material,
    normalize_event,
    redact_for_sync,
    validate_event,
)

BEARER = "curl -H 'Authorization: Bearer sk-live-ABCDEF0123456789xyz' https://api.example.com"
PEM = "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIBmaterialmaterial==\n-----END OPENSSH PRIVATE KEY-----"


def test_inline_token_masked_at_write():
    event = normalize_event("r", "command_started", {"command": BEARER})
    command = event["payload"]["command"]
    assert "sk-live-ABCDEF0123456789xyz" not in command
    assert "[REDACTED]" in command


def test_private_key_masked():
    event = normalize_event("r", "file.read", {"content": PEM})
    assert "material" not in event["payload"]["content"]
    assert "[REDACTED-PRIVATE-KEY]" in event["payload"]["content"]


def test_aws_access_key_masked():
    event = normalize_event("r", "env", {"blob": "AKIAIOSFODNN7EXAMPLE and more text"})
    assert "AKIAIOSFODNN7EXAMPLE" not in event["payload"]["blob"]
    assert "more text" in event["payload"]["blob"]


def test_secret_named_keys_still_structurally_redacted():
    event = normalize_event("r", "x", {"api_key": "supersecretvalue123"})
    assert event["payload"]["api_key"] != "supersecretvalue123"
    assert event["payload"]["api_key"]["redacted"] is True


def test_sensitive_paths_preserved_for_audit():
    # We must still see that the agent touched .env / id_rsa — masking the path
    # would destroy the audit signal; the secret is the file's contents.
    event = normalize_event("r", "command_started", {"command": "cat .env && cat ~/.ssh/id_rsa"})
    assert ".env" in event["payload"]["command"]
    assert "id_rsa" in event["payload"]["command"]


def test_redact_for_sync_is_noop_and_hash_stable_on_written_event():
    event = normalize_event("r", "command_started", {"command": BEARER}, prev_event_hash=None)
    synced = redact_for_sync(event)
    assert synced == event                              # already redacted at write
    assert event_hash(synced) == synced["event_hash"]   # mirror can still verify the chain
    assert validate_event(synced) == []


def test_mask_is_idempotent():
    once = mask_secret_material(BEARER)
    assert mask_secret_material(once) == once

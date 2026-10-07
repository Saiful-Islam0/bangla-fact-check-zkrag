"""Client for the optional local ZK verification-record anchor bridge."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict

import requests


def anchor_claim(storage: Any, claim_id: str) -> Dict[str, Any]:
    record = storage.get_claim_by_id(claim_id)
    if record is None:
        raise FileNotFoundError("Claim not found")
    binding = record.get("input_binding") or {}
    metadata = binding.get("audit_bundle") or {}
    audit_path = metadata.get("audit_bundle_path")
    if not audit_path:
        raise ValueError("Claim has no input-binding audit bundle")

    bridge_url = os.getenv("ZKRAG_ANCHOR_BRIDGE_URL", "").strip().rstrip("/")
    if not bridge_url:
        result = {"status": "not_configured", "error": "ZKRAG_ANCHOR_BRIDGE_URL is not configured"}
        storage.update_anchor_status(claim_id, result)
        return result

    import json
    with open(audit_path, "r", encoding="utf-8") as handle:
        bundle = json.load(handle)
    verification_record = bundle.get("verification_record") or {}
    payload = {
        "schema_version": "zkrag-anchor-record-v1",
        "claim_hash": hashlib.sha256(claim_id.encode("utf-8")).hexdigest(),
        "record_commitment": bundle.get("verification_record_commitment"),
        "verification_record": verification_record,
    }
    try:
        response = requests.post(
            f"{bridge_url}/v1/anchors",
            json=payload,
            timeout=float(os.getenv("ZKRAG_ANCHOR_TIMEOUT_SECONDS", "15")),
        )
        response.raise_for_status()
        result = response.json()
        if result.get("record_commitment") != payload["record_commitment"]:
            raise ValueError("Bridge returned a different record commitment")
        event = result.get("event") or {}
        if (
            result.get("status") != "anchored"
            or not str(result.get("transaction_hash", "")).startswith("0x")
            or not result.get("chain_id")
            or not result.get("contract_address")
            or event.get("name") != "VerificationAnchored"
            or event.get("schema_version") != "1"
            or event.get("verification_record_commitment") != payload["record_commitment"]
            or event.get("claim_hash") != payload["claim_hash"]
        ):
            raise ValueError("Bridge did not return a confirmed anchoring receipt")
    except Exception as exc:
        result = {"status": "failed_retryable", "error": str(exc)}
    storage.update_anchor_status(claim_id, result)
    return result

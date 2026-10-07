#!/usr/bin/env python3
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from input_binding import canonical_json
from zk_anchor import anchor_claim


class StorageStub:
    def __init__(self, audit_path):
        self.record = {"input_binding": {"audit_bundle": {"audit_bundle_path": str(audit_path)}}}
        self.updated = None

    def get_claim_by_id(self, claim_id):
        return self.record if claim_id == "claim-1" else None

    def update_anchor_status(self, claim_id, result):
        self.updated = (claim_id, result)


class ResponseStub:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class AnchorClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.temporary.name) / "audit.json"
        self.record = {"claim_id": "claim-1", "version": "v2"}
        self.commitment = hashlib.sha256(canonical_json(self.record)).hexdigest()
        self.audit_path.write_text(json.dumps({
            "verification_record": self.record,
            "verification_record_commitment": self.commitment,
        }), encoding="utf-8")
        self.storage = StorageStub(self.audit_path)
        self.claim_hash = hashlib.sha256(b"claim-1").hexdigest()

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_bridge_is_explicitly_not_configured(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ZKRAG_ANCHOR_BRIDGE_URL", None)
            result = anchor_claim(self.storage, "claim-1")
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(self.storage.updated[1]["status"], "not_configured")

    def test_confirmed_matching_event_is_accepted(self):
        payload = {
            "status": "anchored", "record_commitment": self.commitment,
            "claim_hash": self.claim_hash, "transaction_hash": "0x1234",
            "chain_id": "31337", "contract_address": "0xcontract",
            "event": {
                "name": "VerificationAnchored", "schema_version": "1",
                "verification_record_commitment": self.commitment,
                "claim_hash": self.claim_hash,
            },
        }
        with mock.patch.dict(os.environ, {"ZKRAG_ANCHOR_BRIDGE_URL": "http://bridge"}), \
             mock.patch("zk_anchor.requests.post", return_value=ResponseStub(payload)):
            result = anchor_claim(self.storage, "claim-1")
        self.assertEqual(result["status"], "anchored")

    def test_wrong_event_is_failed_retryable(self):
        payload = {
            "status": "anchored", "record_commitment": self.commitment,
            "transaction_hash": "0x1234", "chain_id": "31337",
            "contract_address": "0xcontract", "event": {"name": "WrongEvent"},
        }
        with mock.patch.dict(os.environ, {"ZKRAG_ANCHOR_BRIDGE_URL": "http://bridge"}), \
             mock.patch("zk_anchor.requests.post", return_value=ResponseStub(payload)):
            result = anchor_claim(self.storage, "claim-1")
        self.assertEqual(result["status"], "failed_retryable")
        self.assertIn("confirmed anchoring receipt", result["error"])


if __name__ == "__main__":
    unittest.main()

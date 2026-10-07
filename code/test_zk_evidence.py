#!/usr/bin/env python3
"""Focused tests for deterministic evidence commitments and proof records."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path
import numpy as np
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claim_storage import ClaimStorageManager
from zk_evidence import (
    TREE_CAPACITY,
    ZKError,
    build_commitment,
    canonical_json,
    canonicalize_document,
    evidence_digest,
    generate_and_store_proof,
    generate_proof,
    normalize_source,
    select_model_documents,
    verify_proof_package,
    _run_node,
    _package_hash,
)


class DocumentStub:
    def __init__(self, content, source, title="", date=""):
        self.page_content = content
        self.metadata = {"source": source, "title": title, "date": date}


class EmbeddingStub:
    def encode(self, values):
        return np.array([[0.1, 0.2, 0.3] for _ in values], dtype=np.float32)


def documents(count, language="bn"):
    prefix = "বাংলা সংবাদ" if language == "bn" else "English report"
    return [
        DocumentStub(
            f"{prefix} {index}",
            f"HTTPS://Example.COM:443/story/{index}/?utm_source=test&b=2&a=1#fragment",
            f"Title {index}",
            "2026-09-15",
        )
        for index in range(count)
    ]


class EvidenceCommitmentTests(unittest.TestCase):
    def test_bangla_and_english_context_limits_preserve_order(self):
        source = list(range(20))
        self.assertEqual(select_model_documents(source, "bn"), list(range(10)))
        self.assertEqual(select_model_documents(source, "en"), list(range(5)))

    def test_url_normalization(self):
        self.assertEqual(
            normalize_source("HTTPS://Example.COM:443/story/?utm_source=x&b=2&a=1#frag"),
            "https://example.com/story?a=1&b=2",
        )

    def test_bengali_nfc_is_canonical(self):
        composed = unicodedata.normalize("NFC", "ড়")
        decomposed = unicodedata.normalize("NFD", composed)
        left = canonicalize_document(DocumentStub(composed, "submitted_article"), "bn")
        right = canonicalize_document(DocumentStub(decomposed, "submitted_article"), "bn")
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(evidence_digest(left), evidence_digest(right))

    def test_commitment_is_deterministic_and_content_sensitive(self):
        first = build_commitment(documents(10), "bn", {"judge_model": "test"})
        second = build_commitment(documents(10), "bn", {"judge_model": "test"})
        changed_docs = documents(10)
        changed_docs[3].page_content += " changed"
        changed = build_commitment(changed_docs, "bn", {"judge_model": "test"})
        self.assertEqual(first["root"], second["root"])
        self.assertNotEqual(first["root"], changed["root"])
        self.assertEqual(first["document_count"], 10)
        self.assertEqual(len(first["items"]), 10)

        english_docs = documents(20, "en")
        english_selected = select_model_documents(english_docs, "en")
        english_commitment = build_commitment(english_selected, "en", {"judge_model": "test"})
        self.assertEqual(english_commitment["document_count"], 5)
        self.assertEqual(
            [item["canonical_evidence"]["content"] for item in english_commitment["items"]],
            [document.page_content for document in english_selected],
        )

    def test_empty_and_capacity_handling(self):
        self.assertIsNone(build_commitment([], "bn", {}))
        with self.assertRaises(ZKError):
            build_commitment(documents(TREE_CAPACITY + 1), "bn", {})

    def test_verified_proof_updates_only_selected_evidence(self):
        build_dir = Path(__file__).resolve().parent.parent / "zk" / "build"
        if not (build_dir / "evidence_membership_final.zkey").exists():
            self.skipTest("Run zk/scripts/setup.sh to build proving artifacts")

        commitment = build_commitment(documents(5), "bn", {"judge_model": "test"})
        with tempfile.TemporaryDirectory() as root:
            storage = ClaimStorageManager(
                storage_dir=os.path.join(root, "claims"),
                snapshot_dir=os.path.join(root, "snapshots"),
                flagged_sources_dir=os.path.join(root, "flagged"),
                embedding_model=EmbeddingStub(),
            )
            claim_id = storage.save_claim_record(
                claim_text="দাবি",
                claim_text_original="দাবি",
                classification="UNSURE",
                credibility_score=0,
                explanation="test",
                evidence_sources=[],
                zk_commitment=commitment,
            )
            evidence_id = commitment["items"][2]["evidence_id"]
            with mock.patch.dict(os.environ, {"ZKRAG_PROOF_DIR": os.path.join(root, "proofs")}):
                package = generate_and_store_proof(storage, claim_id, evidence_id)
            self.assertTrue(verify_proof_package(package))

            package_path = Path(root) / "proofs" / f"{package['package_hash']}.json"
            self.assertTrue(package_path.exists())
            standalone = subprocess.run(
                ["node", str(build_dir.parent / "scripts" / "verify.mjs"), str(package_path), str(build_dir / "verification_key.json")],
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(standalone.returncode, 0, standalone.stderr)
            self.assertTrue(json.loads(standalone.stdout)["verified"])

            for field, replacement in (
                ("root", "1"),
                ("leaf", "2"),
                ("position", 1),
            ):
                tampered = json.loads(json.dumps(package))
                tampered["public_inputs"][field] = replacement
                public_index = {"root": 0, "leaf": 1, "position": 2}[field]
                tampered["public_signals"][public_index] = str(replacement)
                tampered["package_hash"] = _package_hash(tampered)
                self.assertFalse(verify_proof_package(tampered), field)

            tampered_proof = json.loads(json.dumps(package))
            tampered_proof["proof"]["pi_a"][0] = str(int(tampered_proof["proof"]["pi_a"][0]) + 1)
            tampered_proof["package_hash"] = _package_hash(tampered_proof)
            self.assertFalse(verify_proof_package(tampered_proof))

            wrong_key_hash = json.loads(json.dumps(package))
            wrong_key_hash["verification_key_sha256"] = "0" * 64
            wrong_key_hash["package_hash"] = _package_hash(wrong_key_hash)
            self.assertFalse(verify_proof_package(wrong_key_hash))

            tampered_record = storage.get_claim_by_id(claim_id)
            tampered_record["zk_commitment"]["items"][2]["canonical_evidence"]["content"] += " modified"
            with self.assertRaisesRegex(ZKError, "canonical evidence"):
                generate_proof(tampered_record, evidence_id)

            # A wrong private sibling path cannot produce a witness/proof.
            tree = _run_node(
                "poseidon.mjs",
                {"leaves": [item["leaf"] for item in commitment["items"]], "index": 2},
            )
            tree["siblings"][0] = str(int(tree["siblings"][0]) + 1)
            bad_input = {
                "root": commitment["root"],
                "leaf": commitment["items"][2]["leaf"],
                "index": 2,
                "siblings": tree["siblings"],
            }
            command = [
                "node",
                str(build_dir.parent / "scripts" / "prove.mjs"),
                str(build_dir / "evidence_membership_js" / "evidence_membership.wasm"),
                str(build_dir / "evidence_membership_final.zkey"),
                str(build_dir / "verification_key.json"),
            ]
            rejected = subprocess.run(command, input=json.dumps(bad_input), text=True, capture_output=True, timeout=30)
            self.assertNotEqual(rejected.returncode, 0)

            updated = storage.get_claim_by_id(claim_id)["zk_commitment"]
            self.assertEqual(updated["status"], "membership_verified")
            self.assertEqual(updated["items"][2]["proof_status"], "membership_verified")
            self.assertNotIn("proof_status", updated["items"][1])


if __name__ == "__main__":
    unittest.main()

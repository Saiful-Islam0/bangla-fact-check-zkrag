#!/usr/bin/env python3
import base64
import copy
import json
import os
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from input_binding import (
    canonical_json, compact_input_binding, finalize_audit_bundle, generation_parameters,
    invoke_groq_raw, prompt_build, sha256_hex, store_audit_bundle,
)
from claim_storage import ClaimStorageManager
from zk_evidence import (
    build_commitment, generate_and_store_input_binding_proof, input_verification_key_sha256,
    validate_audit_bundle, verify_input_binding_package,
)


class DocumentStub:
    def __init__(self, content, source):
        self.page_content = content
        self.metadata = {"source": source, "title": source}


MODELS = {"multi_query_model": "model-q", "summarizer_model": "model-s", "judge_model": "model-j"}


class EmbeddingStub:
    def encode(self, values):
        return np.array([[0.1, 0.2] for _ in values], dtype=np.float32)


def fake_call(stage, template, prompt, model, content):
    params = generation_parameters(stage)
    request = {
        "model": model, "messages": [{"role": "user", "content": prompt.decode("utf-8")}],
        "temperature": 0, "top_p": 1, "stream": False,
        "max_completion_tokens": int(params["max_completion_tokens"]),
    }
    response = {"model": model, "system_fingerprint": "fp-test", "choices": [{"message": {"content": content}}]}
    request_bytes, response_bytes = canonical_json(request), canonical_json(response)
    return {
        "stage": stage, "template_version": template,
        "prompt_bytes_b64": base64.b64encode(prompt).decode(), "stage_prompt_hash": sha256_hex(prompt),
        "request_body_b64": base64.b64encode(request_bytes).decode(), "call_request_body_hash": sha256_hex(request_bytes),
        "response_body_b64": base64.b64encode(response_bytes).decode(), "call_response_hash": sha256_hex(response_bytes),
        "assistant_content": content, "requested_model": model, "returned_model": model,
        "system_fingerprint": "fp-test", "generation_parameters": params,
    }


def make_bundle():
    commitment = build_commitment(
        [DocumentStub("বাংলা সংবাদ এক", "https://example.com/1"), DocumentStub("বাংলা সংবাদ দুই", "https://example.com/2")],
        "bn", {"judge_model": "model-j"},
    )
    evidence = [item["canonical_evidence"] for item in commitment["items"]]
    summary_prompt = prompt_build(stage="summary", normalized_claim="বাংলা দাবি", fresh_evidence=evidence, historical_context=[], template_version="summary-bn-v2")
    summary = fake_call("summary", "summary-bn-v2", summary_prompt, "model-s", "সংক্ষিপ্ত প্রমাণ")
    judge_prompt = prompt_build(stage="judge", normalized_claim="বাংলা দাবি", fresh_evidence=[], historical_context=[], template_version="judge-bn-v2", upstream_output=summary["assistant_content"])
    judge = fake_call("judge", "judge-bn-v2", judge_prompt, "model-j", "Classification: UNSURE\nCredibility Score: N/A\nExplanation: অপর্যাপ্ত")
    return finalize_audit_bundle(
        claim_id="claim-test", request_id="request-test", normalized_claim="বাংলা দাবি", language="bn",
        evidence_commitment=commitment, models=MODELS, calls=[summary, judge], classification="UNSURE",
        verdict_text=judge["assistant_content"],
    )


def resign_bundle(bundle):
    bundle.pop("audit_bundle_hash", None)
    bundle["audit_bundle_hash"] = sha256_hex(canonical_json(bundle))


class InputBindingTests(unittest.TestCase):
    def test_raw_groq_transport_capture_excludes_authorization_headers(self):
        request_bytes = b'{"messages":[{"role":"user","content":"hello"}]}'
        response_bytes = b'{"choices":[{"message":{"content":"ok"}}],"model":"returned","system_fingerprint":"fp"}'
        raw = SimpleNamespace(
            http_request=SimpleNamespace(content=request_bytes, headers={"Authorization": "Bearer secret"}),
            http_response=SimpleNamespace(content=response_bytes),
            parse=lambda: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                model="returned", system_fingerprint="fp",
            ),
        )
        class FakeGroq:
            def __init__(self, api_key):
                self.api_key = api_key
                self.with_raw_response = self
                self.chat = self
                self.completions = self
            def create(self, **kwargs):
                self.kwargs = kwargs
                return raw

        with mock.patch.dict(sys.modules, {"groq": SimpleNamespace(Groq=FakeGroq)}):
            captured = invoke_groq_raw(api_key="secret", stage="query", model="requested", prompt_bytes=b"hello")
        self.assertEqual(base64.b64decode(captured["request_body_b64"]), request_bytes)
        self.assertEqual(base64.b64decode(captured["response_body_b64"]), response_bytes)
        self.assertNotIn("secret", json.dumps(captured))
        self.assertEqual(captured["requested_model"], "requested")
        self.assertEqual(captured["returned_model"], "returned")

    def test_valid_bundle_and_python_javascript_prompt_parity(self):
        bundle = make_bundle()
        self.assertTrue(validate_audit_bundle(bundle)["verified"])
        call = bundle["calls"][0]
        vector = {
            "stage": "summary", "normalized_claim": bundle["normalized_claim"],
            "fresh_evidence": bundle["fresh_evidence"], "historical_context": [],
            "template_version": "summary-bn-v2", "upstream_output": "",
        }
        script = os.path.join(os.path.dirname(__file__), "..", "zk", "scripts", "prompt_vector.mjs")
        result = subprocess.run(["node", script], input=json.dumps(vector, ensure_ascii=False), text=True, capture_output=True, check=True)
        js = json.loads(result.stdout)
        self.assertEqual(js["base64"], call["prompt_bytes_b64"])
        self.assertEqual(js["sha256"], call["stage_prompt_hash"])

    def test_evidence_content_order_removal_and_history_substitution_fail(self):
        for mutation in ("content", "order", "remove", "history"):
            bundle = make_bundle()
            if mutation == "content": bundle["fresh_evidence"][0]["content"] += " বদল"
            elif mutation == "order": bundle["fresh_evidence"].reverse()
            elif mutation == "remove": bundle["fresh_evidence"].pop()
            else: bundle["historical_context"] = [bundle["fresh_evidence"].pop()]
            resign_bundle(bundle)
            self.assertFalse(validate_audit_bundle(bundle)["verified"], mutation)

    def test_prompt_model_parameters_nonce_and_response_tampering_fail(self):
        mutations = []
        prompt = make_bundle(); prompt["calls"][0]["prompt_bytes_b64"] = base64.b64encode(b"changed").decode(); mutations.append(prompt)
        model = make_bundle(); model["calls"][0]["requested_model"] = "other"; mutations.append(model)
        params = make_bundle(); params["calls"][0]["generation_parameters"]["temperature"] = "1"; mutations.append(params)
        template = make_bundle(); template["templates"]["summary-bn-v2"] += " changed"; mutations.append(template)
        nonce = make_bundle(); nonce["request_id"] = "other-request"; mutations.append(nonce)
        swapped = make_bundle(); swapped["calls"][0]["response_body_b64"], swapped["calls"][1]["response_body_b64"] = swapped["calls"][1]["response_body_b64"], swapped["calls"][0]["response_body_b64"]; mutations.append(swapped)
        for index, bundle in enumerate(mutations):
            resign_bundle(bundle)
            self.assertFalse(validate_audit_bundle(bundle)["verified"], index)

    def test_real_aggregate_groth16_proof_and_standalone_verifier(self):
        repo = Path(__file__).resolve().parent.parent
        build = repo / "zk" / "build" / "input_binding_v2"
        if not (build / "evidence_input_binding_final.zkey").exists():
            self.skipTest("Run zk/scripts/setup_input_binding.sh first")
        bundle = make_bundle()
        # Production bundles bind the concrete v2 verification key.
        bundle["verification_record"]["verification_key_sha256"] = input_verification_key_sha256()
        bundle["verification_record_commitment"] = sha256_hex(canonical_json(bundle["verification_record"]))
        resign_bundle(bundle)
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {
            "ZKRAG_AUDIT_DIR": os.path.join(root, "audits"),
            "ZKRAG_PROOF_DIR": os.path.join(root, "proofs"),
        }):
            stored = store_audit_bundle(bundle)
            binding = compact_input_binding(bundle, stored)
            commitment = build_commitment(
                [DocumentStub("বাংলা সংবাদ এক", "https://example.com/1"), DocumentStub("বাংলা সংবাদ দুই", "https://example.com/2")],
                "bn", {"judge_model": "model-j"},
            )
            commitment["input_binding"] = binding
            storage = ClaimStorageManager(
                storage_dir=os.path.join(root, "claims"), snapshot_dir=os.path.join(root, "snapshots"),
                flagged_sources_dir=os.path.join(root, "flagged"), embedding_model=EmbeddingStub(),
            )
            storage.save_claim_record(
                claim_text="বাংলা দাবি", claim_text_original="বাংলা দাবি", classification="UNSURE",
                credibility_score=0, explanation="অপর্যাপ্ত", evidence_sources=[], zk_commitment=commitment,
                input_binding=binding, claim_id="claim-test",
            )
            package = generate_and_store_input_binding_proof(storage, "claim-test")
            self.assertTrue(verify_input_binding_package(package)["verified"])
            tampered_inputs = copy.deepcopy(package)
            tampered_inputs["public_inputs"]["root"] = "1"
            tampered_inputs.pop("package_hash")
            tampered_inputs["package_hash"] = sha256_hex(canonical_json(tampered_inputs))
            self.assertFalse(verify_input_binding_package(tampered_inputs)["verified"])
            tampered_signals = copy.deepcopy(package)
            tampered_signals["public_signals"][1] = "1"
            tampered_signals.pop("package_hash")
            tampered_signals["package_hash"] = sha256_hex(canonical_json(tampered_signals))
            self.assertFalse(verify_input_binding_package(tampered_signals)["verified"])
            tampered_proof = copy.deepcopy(package)
            tampered_proof["proof"]["pi_a"][0] = str(int(tampered_proof["proof"]["pi_a"][0]) + 1)
            tampered_proof.pop("package_hash")
            tampered_proof["package_hash"] = sha256_hex(canonical_json(tampered_proof))
            self.assertFalse(verify_input_binding_package(tampered_proof)["verified"])
            wrong_key = copy.deepcopy(package)
            wrong_key["verification_key_sha256"] = "0" * 64
            wrong_key.pop("package_hash")
            wrong_key["package_hash"] = sha256_hex(canonical_json(wrong_key))
            self.assertFalse(verify_input_binding_package(wrong_key)["verified"])
            package_path = Path(root) / "package.json"
            package_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
            standalone = subprocess.run(
                ["node", str(repo / "zk" / "scripts" / "verify.mjs"), str(package_path), str(build / "verification_key.json")],
                text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(standalone.returncode, 0, standalone.stderr)
            self.assertTrue(json.loads(standalone.stdout)["verified"])


if __name__ == "__main__":
    unittest.main()

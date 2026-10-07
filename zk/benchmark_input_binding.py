#!/usr/bin/env python3
"""Benchmark the aggregate v2 proof after one warm-up and five measured runs."""
import base64
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from input_binding import (
    canonical_json, compact_input_binding, finalize_audit_bundle, generation_parameters,
    prompt_build, sha256_hex, store_audit_bundle,
)
from zk_evidence import (
    CIRCUIT_VERSION, HASH_ALGORITHM, SCHEMA_VERSION, TREE_CAPACITY, TREE_HEIGHT,
    _run_node, canonicalize_document, evidence_digest, generate_input_binding_proof,
    input_verification_key_sha256, verify_input_binding_package,
)


class Document:
    def __init__(self, index):
        self.page_content = f"বাংলা পরীক্ষামূলক প্রমাণ নথি {index}"
        self.metadata = {"source": f"https://example.com/bn/{index}", "title": f"নথি {index}", "date": "2026-09-15"}


MODELS = {"multi_query_model": "benchmark-query", "summarizer_model": "benchmark-summary", "judge_model": "benchmark-judge"}


def fake_call(stage, template, prompt, model, content):
    params = generation_parameters(stage)
    request = {"model": model, "messages": [{"role": "user", "content": prompt.decode()}], "temperature": 0, "top_p": 1, "stream": False, "max_completion_tokens": int(params["max_completion_tokens"])}
    response = {"model": model, "system_fingerprint": "benchmark", "choices": [{"message": {"content": content}}]}
    request_bytes, response_bytes = canonical_json(request), canonical_json(response)
    return {"stage": stage, "template_version": template, "prompt_bytes_b64": base64.b64encode(prompt).decode(), "stage_prompt_hash": sha256_hex(prompt), "request_body_b64": base64.b64encode(request_bytes).decode(), "call_request_body_hash": sha256_hex(request_bytes), "response_body_b64": base64.b64encode(response_bytes).decode(), "call_response_hash": sha256_hex(response_bytes), "assistant_content": content, "requested_model": model, "returned_model": model, "system_fingerprint": "benchmark", "generation_parameters": params}


def prepare(count, audit_dir):
    docs = [Document(i) for i in range(count)]
    start = time.perf_counter()
    evidence = [canonicalize_document(doc, "bn") for doc in docs]
    digests = [evidence_digest(item) for item in evidence]
    canonical_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    tree = _run_node("poseidon.mjs", {"digestParts": [{"hi": item["hi"], "lo": item["lo"]} for item in digests]})
    tree_ms = (time.perf_counter() - start) * 1000
    commitment = {"status": "committed_unproven", "root": tree["root"], "document_count": count, "tree_capacity": TREE_CAPACITY, "tree_height": TREE_HEIGHT, "schema_version": SCHEMA_VERSION, "hash_algorithm": HASH_ALGORITHM, "circuit_version": CIRCUIT_VERSION, "model_provenance": MODELS, "items": [{"position": i, "evidence_id": d["evidence_id"], "sha256": d["sha256"], "canonical_evidence": evidence[i], "leaf": tree["leaves"][i]} for i, d in enumerate(digests)], "proofs": []}
    start = time.perf_counter()
    p1 = prompt_build(stage="summary", normalized_claim="বাংলা বেঞ্চমার্ক দাবি", fresh_evidence=evidence, historical_context=[], template_version="summary-bn-v2")
    summary = fake_call("summary", "summary-bn-v2", p1, MODELS["summarizer_model"], "বেঞ্চমার্ক সারসংক্ষেপ")
    p2 = prompt_build(stage="judge", normalized_claim="বাংলা বেঞ্চমার্ক দাবি", fresh_evidence=[], historical_context=[], template_version="judge-bn-v2", upstream_output=summary["assistant_content"])
    judge = fake_call("judge", "judge-bn-v2", p2, MODELS["judge_model"], "Classification: UNSURE\nCredibility Score: N/A\nExplanation: benchmark")
    bundle = finalize_audit_bundle(claim_id=f"benchmark-{count}", request_id=f"benchmark-request-{count}", normalized_claim="বাংলা বেঞ্চমার্ক দাবি", language="bn", evidence_commitment=commitment, models=MODELS, calls=[summary, judge], classification="UNSURE", verdict_text=judge["assistant_content"], verification_key_sha256=input_verification_key_sha256(), completed_at="2026-09-15T00:00:00+00:00")
    prompt_commitment_ms = (time.perf_counter() - start) * 1000
    os.environ["ZKRAG_AUDIT_DIR"] = audit_dir
    binding = compact_input_binding(bundle, store_audit_bundle(bundle))
    commitment["input_binding"] = binding
    return {"claim_id": f"benchmark-{count}", "zk_commitment": commitment, "input_binding": binding}, canonical_ms, tree_ms, prompt_commitment_ms


def measure(count, audit_dir):
    record, canonical_ms, tree_ms, prompt_ms = prepare(count, audit_dir)
    start = time.perf_counter(); package = generate_input_binding_proof(record); proof_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter(); verified = verify_input_binding_package(package)["verified"]; verification_ms = (time.perf_counter() - start) * 1000
    if not verified: raise RuntimeError("Aggregate benchmark proof failed")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"canonical_commitment_ms": canonical_ms, "poseidon_tree_ms": tree_ms, "prompt_commitment_ms": prompt_ms, "proof_ms": proof_ms, "verification_ms": verification_ms, "proof_package_bytes": len(canonical_json(package)), "peak_parent_rss_bytes": rss if platform.system() == "Darwin" else rss * 1024}


def main():
    with tempfile.TemporaryDirectory() as root:
        output = {"generated_at": "2026-09-15", "warmup_runs_per_case": 1, "measured_runs_per_case": 5, "environment": {"platform": platform.platform(), "python": platform.python_version(), "node": subprocess.check_output(["node", "--version"], text=True).strip(), "circuit": "evidence-input-binding-16-v2", "constraints": 11075}, "cases": {}}
        for count in (1, 5, 10):
            measure(count, root)
            runs = [measure(count, root) for _ in range(5)]
            output["cases"][str(count)] = {key: {"median": statistics.median(run[key] for run in runs), "min": min(run[key] for run in runs), "max": max(run[key] for run in runs)} for key in runs[0]}
        rendered = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
        destination = ROOT / "zk" / "benchmark_results_v2.json"
        destination.write_text(rendered, encoding="utf-8")
        print(f"Wrote {destination}")


if __name__ == "__main__": main()

#!/usr/bin/env python3
"""Benchmark commitment, proving, verification, package size, and peak RSS."""

import json
import resource
import statistics
import sys
import time
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from zk_evidence import (
    CIRCUIT_VERSION,
    HASH_ALGORITHM,
    SCHEMA_VERSION,
    TREE_CAPACITY,
    TREE_HEIGHT,
    _run_node,
    canonicalize_document,
    evidence_digest,
    generate_proof,
    verify_proof_package,
)


class Document:
    def __init__(self, index):
        self.page_content = f"বাংলা পরীক্ষামূলক প্রমাণ নথি {index}"
        self.metadata = {"source": f"https://example.com/bn/{index}", "title": f"নথি {index}", "date": "2026-09-15"}


def measure(count):
    docs = [Document(index) for index in range(count)]
    start = time.perf_counter()
    evidence = [canonicalize_document(document, "bn") for document in docs]
    digests = [evidence_digest(item) for item in evidence]
    commitment_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    tree = _run_node("poseidon.mjs", {"digestParts": [{"hi": item["hi"], "lo": item["lo"]} for item in digests]})
    tree_ms = (time.perf_counter() - start) * 1000
    items = [
        {
            "position": index,
            "evidence_id": digest["evidence_id"],
            "sha256": digest["sha256"],
            "canonical_evidence": evidence[index],
            "leaf": tree["leaves"][index],
        }
        for index, digest in enumerate(digests)
    ]
    commitment = {
        "status": "committed_unproven",
        "root": tree["root"],
        "document_count": count,
        "tree_capacity": TREE_CAPACITY,
        "tree_height": TREE_HEIGHT,
        "schema_version": SCHEMA_VERSION,
        "hash_algorithm": HASH_ALGORITHM,
        "circuit_version": CIRCUIT_VERSION,
        "model_provenance": {"judge_model": "benchmark"},
        "items": items,
        "proofs": [],
    }

    record = {"claim_id": f"benchmark-{count}", "zk_commitment": commitment}
    evidence_id = commitment["items"][0]["evidence_id"]
    start = time.perf_counter()
    package = generate_proof(record, evidence_id)
    proof_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    verified = verify_proof_package(package)
    verification_ms = (time.perf_counter() - start) * 1000
    if not verified:
        raise RuntimeError("Benchmark proof did not verify")
    return {
        "canonical_commitment_ms": commitment_ms,
        "poseidon_tree_ms": tree_ms,
        "proof_ms": proof_ms,
        "verification_ms": verification_ms,
        "proof_package_bytes": len(json.dumps(package, separators=(",", ":")).encode()),
        "peak_rss_bytes": (
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if platform.system() == "Darwin"
            else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        ),
    }


def main():
    output = {
        "warmup_runs": 1,
        "measured_runs": 5,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "circuit": CIRCUIT_VERSION,
        },
        "cases": {},
    }
    for count in (1, 5, 10):
        measure(count)
        runs = [measure(count) for _ in range(5)]
        output["cases"][str(count)] = {
            key: {
                "median": statistics.median(run[key] for run in runs),
                "min": min(run[key] for run in runs),
                "max": max(run[key] for run in runs),
            }
            for key in runs[0]
        }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

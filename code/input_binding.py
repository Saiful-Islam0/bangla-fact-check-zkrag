"""Deterministic model-input construction and v2 audit commitments.

The module deliberately keeps model inference outside the ZK statement.  It
captures the exact Groq request/response bodies and creates commitments that a
standalone verifier can reproduce from a disclosed audit bundle.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROTOCOL_VERSION = "zkrag-input-binding-v2"
CANONICALIZATION_VERSION = "nfc-rfc8785-subset-v1"
PROMPT_BUILD_VERSION = "zkrag-prompt-build-v2"
TEMPLATE_REGISTRY_VERSION = "zkrag-template-registry-v2"
MODEL_PIPELINE_VERSION = "groq-evidence-pipeline-v2"
GENERATION_CONFIG_VERSION = "groq-generation-v2"
AUDIT_BUNDLE_VERSION = "zkrag-audit-bundle-v2"
INPUT_CIRCUIT_VERSION = "evidence-input-binding-16-v2"
INPUT_PACKAGE_VERSION = "zkrag-input-binding-package-v2"
TRANSCRIPT_DOMAIN = b"zkrag:transcript:v2\x00"


TEMPLATES: Dict[str, str] = {
    "query-en-v2": (
        "Generate exactly three newline-separated search queries for fact-checking "
        "the claim. Cover the main event, named people or organisations, and relevant "
        "place or time. Return queries only."
    ),
    "summary-en-v2": (
        "Extract concise factual evidence relevant to the claim. Use only the supplied "
        "fresh evidence, identify support or contradiction, and retain source/date "
        "references when available."
    ),
    "summary-bn-v2": (
        "সরবরাহ করা নতুন প্রমাণ থেকেই দাবির সঙ্গে সম্পর্কিত ঘটনামূলক তথ্য সংক্ষেপে "
        "বের করো। সম্ভব হলে উৎস ও তারিখ উল্লেখ করো।"
    ),
    "judge-en-v2": (
        "Classify the claim using only the supplied evidence summary. Respond exactly "
        "with Classification: REAL or FAKE or MISINFORMATION or UNSURE, Credibility "
        "Score: 0-100 (or N/A for UNSURE), and Explanation."
    ),
    "judge-bn-v2": (
        "শুধু সরবরাহ করা প্রমাণের সারসংক্ষেপ ব্যবহার করে দাবিকে REAL, FAKE, "
        "MISINFORMATION অথবা UNSURE হিসেবে শ্রেণিবদ্ধ করো। ঠিক এই বিন্যাসে উত্তর দাও: "
        "Classification, Credibility Score, Explanation। ব্যাখ্যা বাংলায় লিখবে।"
    ),
}


def nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [nfc(item) for item in value]
    if isinstance(value, dict):
        return {str(key): nfc(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> bytes:
    """RFC-8785-compatible encoding for this protocol's integer/string schema."""
    return json.dumps(
        nfc(value), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_id(data: bytes) -> str:
    return f"sha256:{sha256_hex(data)}"


def digest_limbs(hex_digest: str) -> Dict[str, str]:
    raw = bytes.fromhex(hex_digest.removeprefix("sha256:"))
    if len(raw) != 32:
        raise ValueError("Expected a SHA-256 digest")
    return {
        "hi": str(int.from_bytes(raw[:16], "big")),
        "lo": str(int.from_bytes(raw[16:], "big")),
    }


def normalize_claim(value: str) -> str:
    """Versioned equivalent of the legacy claim cleanup plus Unicode NFC."""
    return unicodedata.normalize("NFC", str(value or "")).replace("'", "").replace("\n", " ").strip()


def _field(name: str, value: bytes) -> bytes:
    return name.encode("ascii") + b":" + str(len(value)).encode("ascii") + b"\n" + value + b"\n"


def prompt_build(
    *,
    stage: str,
    normalized_claim: str,
    fresh_evidence: Iterable[Dict[str, Any]],
    historical_context: Iterable[Dict[str, Any]],
    template_version: str,
    upstream_output: str = "",
) -> bytes:
    """Build the exact UTF-8 user-message bytes sent to the model.

    Length prefixes make separators unambiguous even when Bengali evidence or
    retrieved text itself contains section-like strings.
    """
    if template_version not in TEMPLATES:
        raise ValueError(f"Unsupported prompt template: {template_version}")
    fresh = [canonical_json(item) for item in fresh_evidence]
    history = [canonical_json(item) for item in historical_context]
    parts = [
        b"ZKRAG-PROMPT-BUILD/2\n",
        _field("prompt_build_version", PROMPT_BUILD_VERSION.encode("ascii")),
        _field("stage", nfc(stage).encode("utf-8")),
        _field("template_version", template_version.encode("ascii")),
        _field("instruction", nfc(TEMPLATES[template_version]).encode("utf-8")),
        _field("normalized_claim", nfc(normalized_claim).encode("utf-8")),
        _field("fresh_evidence_count", str(len(fresh)).encode("ascii")),
    ]
    for index, item in enumerate(fresh):
        parts.append(_field(f"fresh_evidence_{index}", item))
    parts.append(_field("historical_context_count", str(len(history)).encode("ascii")))
    for index, item in enumerate(history):
        parts.append(_field(f"historical_context_{index}", item))
    parts.append(_field("upstream_output", nfc(upstream_output).encode("utf-8")))
    return b"".join(parts)


def generation_parameters(stage: str) -> Dict[str, str]:
    return {
        "temperature": "0",
        "top_p": "1",
        "stream": "false",
        "max_completion_tokens": "256" if stage == "query" else "1024",
    }


def model_pipeline(language: str, models: Dict[str, str]) -> List[Dict[str, Any]]:
    stages = ["summary", "judge"] if language == "bn" else ["query", "summary", "judge"]
    key_for = {"query": "multi_query_model", "summary": "summarizer_model", "judge": "judge_model"}
    return [
        {
            "position": str(position),
            "stage": stage,
            "model_id": str(models[key_for[stage]]),
            "generation_parameters": generation_parameters(stage),
        }
        for position, stage in enumerate(stages)
    ]


def invoke_groq_raw(*, api_key: str, stage: str, model: str, prompt_bytes: bytes) -> Dict[str, Any]:
    """Call Groq while retaining exact body bytes; secrets/headers are excluded."""
    from groq import Groq

    prompt_text = prompt_bytes.decode("utf-8")
    params = generation_parameters(stage)
    client = Groq(api_key=api_key)
    raw = client.with_raw_response.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=0,
        top_p=1,
        stream=False,
        max_completion_tokens=int(params["max_completion_tokens"]),
    )
    parsed = raw.parse()
    request_body = bytes(raw.http_request.content or b"")
    response_body = bytes(raw.http_response.content or b"")
    assistant_content = parsed.choices[0].message.content or ""
    return {
        "stage": stage,
        "template_version": "",
        "prompt_bytes_b64": base64.b64encode(prompt_bytes).decode("ascii"),
        "stage_prompt_hash": sha256_hex(prompt_bytes),
        "request_body_b64": base64.b64encode(request_body).decode("ascii"),
        "call_request_body_hash": sha256_hex(request_body),
        "response_body_b64": base64.b64encode(response_body).decode("ascii"),
        "call_response_hash": sha256_hex(response_body),
        "assistant_content": nfc(assistant_content),
        "requested_model": model,
        "returned_model": str(getattr(parsed, "model", "") or ""),
        "system_fingerprint": str(getattr(parsed, "system_fingerprint", "") or ""),
        "generation_parameters": params,
    }


def request_object(
    *,
    claim_id: str,
    request_id: str,
    evidence_root: str,
    document_count: int,
    prompt_hash: str,
    pipeline: List[Dict[str, Any]],
    versions: Dict[str, str],
    resolved_models: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "document_count": str(document_count),
        "evidence_root": str(evidence_root),
        "model_pipeline": pipeline,
        "resolved_models": list(resolved_models or []),
        "prompt_hash": prompt_hash,
        "request_id": request_id,
        "versions": dict(versions),
    }


def _transcript_hash(calls: List[Dict[str, Any]]) -> str:
    cursor = hashlib.sha256(TRANSCRIPT_DOMAIN).digest()
    for position, call in enumerate(calls):
        link = {
            "call_request_body_hash": call["call_request_body_hash"],
            "call_response_hash": call["call_response_hash"],
            "position": str(position),
            "previous": cursor.hex(),
            "stage": call["stage"],
            "stage_prompt_hash": call["stage_prompt_hash"],
        }
        cursor = hashlib.sha256(TRANSCRIPT_DOMAIN + canonical_json(link)).digest()
    return cursor.hex()


def protocol_versions(evidence_commitment: Dict[str, Any]) -> Dict[str, str]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "evidence_schema_version": str(evidence_commitment.get("schema_version", "")),
        "canonicalization_version": CANONICALIZATION_VERSION,
        "prompt_build_version": PROMPT_BUILD_VERSION,
        "template_registry_version": TEMPLATE_REGISTRY_VERSION,
        "model_pipeline_version": MODEL_PIPELINE_VERSION,
        "generation_config_version": GENERATION_CONFIG_VERSION,
        "circuit_version": INPUT_CIRCUIT_VERSION,
        "membership_package_version": "zkrag-membership-package-v2",
        "input_package_version": INPUT_PACKAGE_VERSION,
        "audit_bundle_version": AUDIT_BUNDLE_VERSION,
    }


def finalize_audit_bundle(
    *,
    claim_id: str,
    request_id: str,
    normalized_claim: str,
    language: str,
    evidence_commitment: Dict[str, Any],
    models: Dict[str, str],
    calls: List[Dict[str, Any]],
    classification: str,
    verdict_text: str,
    historical_context: Optional[List[Dict[str, Any]]] = None,
    completed_at: Optional[str] = None,
    verification_key_sha256: str = "",
) -> Dict[str, Any]:
    evidence = [item["canonical_evidence"] for item in evidence_commitment.get("items", [])]
    history = list(historical_context or [])
    summary_call = next((call for call in calls if call.get("stage") == "summary"), None)
    judge_call = next((call for call in calls if call.get("stage") == "judge"), None)
    if summary_call is None or judge_call is None:
        raise ValueError("A complete audit bundle requires summary and judge calls")
    versions = protocol_versions(evidence_commitment)
    pipeline = model_pipeline(language, models)
    resolved_models = [
        {
            "stage": call["stage"],
            "requested_model": call["requested_model"],
            "returned_model": call.get("returned_model", ""),
            "system_fingerprint": call.get("system_fingerprint", ""),
        }
        for call in calls
    ]
    prompt_hash = summary_call["stage_prompt_hash"]
    req_object = request_object(
        claim_id=claim_id,
        request_id=request_id,
        evidence_root=evidence_commitment["root"],
        document_count=len(evidence),
        prompt_hash=prompt_hash,
        pipeline=pipeline,
        versions=versions,
        resolved_models=resolved_models,
    )
    req_hash = sha256_hex(canonical_json(req_object))
    transcript_hash = _transcript_hash(calls)
    completed = completed_at or datetime.now(timezone.utc).isoformat()
    response_hash = judge_call["call_response_hash"]
    verification_record = {
        "claim_id": claim_id,
        "classification": classification,
        "completed_at": completed,
        "document_count": str(len(evidence)),
        "evidence_root": evidence_commitment["root"],
        "model_pipeline": pipeline,
        "resolved_models": resolved_models,
        "prompt_hash": prompt_hash,
        "request_hash": req_hash,
        "response_hash": response_hash,
        "transcript_hash": transcript_hash,
        "verdict_text": nfc(verdict_text),
        "verification_key_sha256": verification_key_sha256,
        "versions": versions,
    }
    record_commitment = sha256_hex(canonical_json(verification_record))
    bundle = {
        "audit_bundle_version": AUDIT_BUNDLE_VERSION,
        "claim_id": claim_id,
        "request_id": request_id,
        "normalized_claim": nfc(normalized_claim),
        "language": language,
        "fresh_evidence": evidence,
        "historical_context": history,
        "template_registry_version": TEMPLATE_REGISTRY_VERSION,
        "templates": {
            version: TEMPLATES[version]
            for version in dict.fromkeys(call["template_version"] for call in calls)
        },
        "calls": calls,
        "request_object": req_object,
        "prompt_hash": prompt_hash,
        "request_hash": req_hash,
        "response_hash": response_hash,
        "transcript_hash": transcript_hash,
        "classification": classification,
        "verdict_text": nfc(verdict_text),
        "completed_at": completed,
        "verification_record": verification_record,
        "verification_record_commitment": record_commitment,
        "versions": versions,
    }
    bundle["audit_bundle_hash"] = sha256_hex(canonical_json(bundle))
    return bundle


def audit_storage_dir() -> Path:
    path = Path(os.getenv("ZKRAG_AUDIT_DIR", str(Path(__file__).resolve().parent / "zk_audits")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_audit_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    expected = bundle.get("audit_bundle_hash")
    without_hash = {key: value for key, value in bundle.items() if key != "audit_bundle_hash"}
    if expected != sha256_hex(canonical_json(without_hash)):
        raise ValueError("Audit bundle hash mismatch")
    output = audit_storage_dir() / f"{expected}.json"
    fd, temporary = tempfile.mkstemp(prefix=".audit-", suffix=".tmp", dir=audit_storage_dir())
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(bundle, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return {
        "audit_bundle_hash": expected,
        "audit_bundle_path": str(output),
        "audit_bundle_version": AUDIT_BUNDLE_VERSION,
    }


def new_request_id() -> str:
    return str(uuid.uuid4())


def compact_input_binding(bundle: Dict[str, Any], stored: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "committed_unproven",
        "membership_status": "committed_unproven",
        "aggregate_proof_status": "unproven",
        "evidence_ids": [hash_id(canonical_json(item)) for item in bundle["fresh_evidence"]],
        "model_pipeline": bundle["request_object"]["model_pipeline"],
        "resolved_models": bundle["verification_record"]["resolved_models"],
        "template_versions": [call["template_version"] for call in bundle["calls"]],
        "package_versions": {
            "audit": AUDIT_BUNDLE_VERSION,
            "aggregate": INPUT_PACKAGE_VERSION,
            "membership": "zkrag-membership-package-v2",
        },
        "prompt_hash": bundle["prompt_hash"],
        "request_hash": bundle["request_hash"],
        "response_hash": bundle["response_hash"],
        "transcript_hash": bundle["transcript_hash"],
        "verification_record_commitment": bundle["verification_record_commitment"],
        "versions": bundle["versions"],
        "audit_bundle": stored,
        "zk_onchain_anchor": False,
        "anchor_status": "not_configured",
    }

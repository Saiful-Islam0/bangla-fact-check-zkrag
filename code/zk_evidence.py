"""Versioned membership and aggregate input-binding proof orchestration.

The circuits prove Merkle relations and digest binding only. They do not prove
that retrieved evidence is true, that retrieval was complete, or that the model
reasoned correctly from the evidence.
"""

from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import subprocess
import threading
import unicodedata
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from input_binding import (
    AUDIT_BUNDLE_VERSION,
    INPUT_CIRCUIT_VERSION,
    INPUT_PACKAGE_VERSION,
    MODEL_PIPELINE_VERSION,
    PROMPT_BUILD_VERSION,
    PROTOCOL_VERSION,
    TEMPLATE_REGISTRY_VERSION,
    TEMPLATES,
    _transcript_hash,
    canonical_json as binding_canonical_json,
    digest_limbs,
    generation_parameters,
    prompt_build,
    request_object,
    sha256_hex,
)


SCHEMA_VERSION = "zkrag-evidence-v1"
HASH_ALGORITHM = "sha256-poseidon-bn254-v1"
CIRCUIT_VERSION = "evidence-membership-16-v1"
TREE_CAPACITY = 16
TREE_HEIGHT = 4
MODEL_CONTEXT_LIMITS = {"bn": 10, "en": 5}
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_PROOF_LOCK = threading.Lock()


class ZKError(RuntimeError):
    """Raised when evidence commitment or proof tooling fails."""


def select_model_documents(documents: Iterable[Any], language: str) -> List[Any]:
    """Apply the explicit Bangla-first context limits without reordering."""
    language_code = "bn" if str(language).lower() in {"bn", "bengali", "bn-in", "bn-bd"} else "en"
    return list(documents)[:MODEL_CONTEXT_LIMITS[language_code]]


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _nfc(item) for key, item in value.items()}
    return value


def normalize_source(source: Optional[str]) -> str:
    """Normalize a web URL while retaining non-URL source identifiers."""
    raw = unicodedata.normalize("NFC", str(source or "")).strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return raw

        scheme = parts.scheme.lower()
        hostname = parts.hostname.lower().encode("idna").decode("ascii")
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = parts.port
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            hostname = f"{hostname}:{port}"

        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if path != "/":
            path = path.rstrip("/") or "/"
        query_pairs = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
        ]
        query_pairs.sort()
        return urlunsplit((scheme, hostname, path, urlencode(query_pairs, doseq=True), ""))
    except (UnicodeError, ValueError):
        return raw


def canonical_json(value: Dict[str, Any]) -> bytes:
    """Serialize this string-only schema using the RFC 8785 JSON form.

    The evidence schema contains strings only, avoiding RFC 8785's special
    floating-point serialization cases.
    """
    normalized = _nfc(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonicalize_document(document: Any, language: str) -> Dict[str, str]:
    metadata = getattr(document, "metadata", None) or {}
    content = getattr(document, "page_content", None)
    if content is None and isinstance(document, dict):
        metadata = document.get("metadata") or document
        content = document.get("page_content", document.get("content", ""))

    source = str(metadata.get("source") or metadata.get("url") or "")
    source_type = str(metadata.get("source_type") or ("submitted" if source in {"submitted_article", "submitted_url"} else "web"))
    language_code = "bn" if str(language).lower() in {"bn", "bengali", "bn-in", "bn-bd"} else "en"
    return _nfc({
        "content": str(content or ""),
        "language": language_code,
        "publication_date": str(metadata.get("date") or ""),
        "schema_version": SCHEMA_VERSION,
        "source": normalize_source(source),
        "source_type": source_type,
        "title": str(metadata.get("title") or ""),
    })


def evidence_digest(evidence: Dict[str, Any]) -> Dict[str, Any]:
    digest = hashlib.sha256(canonical_json(evidence)).digest()
    return {
        "evidence_id": f"sha256:{digest.hex()}",
        "sha256": digest.hex(),
        "hi": str(int.from_bytes(digest[:16], "big")),
        "lo": str(int.from_bytes(digest[16:], "big")),
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _zk_root() -> Path:
    return Path(os.getenv("ZKRAG_ZK_ROOT", str(_repo_root() / "zk"))).resolve()


def _run_node(
    script: str,
    payload: Dict[str, Any],
    timeout: Optional[int] = None,
    args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    script_path = _zk_root() / "scripts" / script
    if not script_path.exists():
        raise ZKError(f"Missing ZK script: {script_path}")
    command = [os.getenv("ZKRAG_NODE_BINARY", "node"), str(script_path), *(args or [])]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout or int(os.getenv("ZKRAG_ZK_TIMEOUT_SECONDS", "120")),
            cwd=str(_zk_root()),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ZKError(f"ZK tool execution failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise ZKError(f"ZK tool failed: {detail[-1000:]}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ZKError("ZK tool returned invalid JSON") from exc


def build_commitment(documents: Iterable[Any], language: str, model_provenance: Dict[str, str]) -> Optional[Dict[str, Any]]:
    docs = list(documents)
    if not docs:
        return None
    if len(docs) > TREE_CAPACITY:
        raise ZKError(f"Evidence count {len(docs)} exceeds circuit capacity {TREE_CAPACITY}")

    items: List[Dict[str, Any]] = []
    digest_parts = []
    for position, document in enumerate(docs):
        evidence = canonicalize_document(document, language)
        digest = evidence_digest(evidence)
        digest_parts.append({"hi": digest["hi"], "lo": digest["lo"]})
        items.append({
            "position": position,
            "evidence_id": digest["evidence_id"],
            "sha256": digest["sha256"],
            "canonical_evidence": evidence,
        })

    tree = _run_node("poseidon.mjs", {"digestParts": digest_parts})
    for item, leaf in zip(items, tree["leaves"]):
        item["leaf"] = leaf

    return {
        "status": "committed_unproven",
        "root": tree["root"],
        "document_count": len(items),
        "tree_capacity": TREE_CAPACITY,
        "tree_height": TREE_HEIGHT,
        "schema_version": SCHEMA_VERSION,
        "hash_algorithm": HASH_ALGORITHM,
        "circuit_version": CIRCUIT_VERSION,
        "model_provenance": dict(model_provenance),
        "items": items,
        "proofs": [],
        "zk_onchain_anchor": False,
        "anchor_status": "unsupported_by_current_bridge",
    }


def commitment_summary(commitment: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not commitment:
        return None
    summary = {
        key: commitment.get(key)
        for key in (
            "status", "root", "document_count", "tree_capacity", "schema_version",
            "hash_algorithm", "circuit_version", "zk_onchain_anchor", "anchor_status",
        )
    }
    summary["evidence"] = [
        {
            "position": item.get("position"),
            "evidence_id": item.get("evidence_id"),
            "source": (item.get("canonical_evidence") or {}).get("source"),
            "title": (item.get("canonical_evidence") or {}).get("title"),
            "proof_status": item.get("proof_status", "unproven"),
        }
        for item in commitment.get("items", [])
    ]
    if isinstance(commitment.get("input_binding"), dict):
        summary["input_binding"] = dict(commitment["input_binding"])
    return summary


def _artifact_paths() -> Dict[str, Path]:
    build = _zk_root() / "build"
    return {
        "wasm": build / "evidence_membership_js" / "evidence_membership.wasm",
        "zkey": build / "evidence_membership_final.zkey",
        "verification_key": build / "verification_key.json",
    }


def _input_artifact_paths() -> Dict[str, Path]:
    build = _zk_root() / "build" / "input_binding_v2"
    return {
        "wasm": build / "evidence_input_binding_js" / "evidence_input_binding.wasm",
        "zkey": build / "evidence_input_binding_final.zkey",
        "verification_key": build / "verification_key.json",
    }


@contextmanager
def _serialized_proof_generation():
    """Serialize memory-intensive proving across threads and worker processes."""
    with _PROOF_LOCK:
        lock_path = proof_storage_dir() / ".generation.lock"
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_hash(package: Dict[str, Any]) -> str:
    hashable = {key: value for key, value in package.items() if key != "package_hash"}
    return hashlib.sha256(canonical_json(hashable)).hexdigest()


def generate_proof(record: Dict[str, Any], evidence_id: str) -> Dict[str, Any]:
    commitment = record.get("zk_commitment") or {}
    items = commitment.get("items") or []
    selected = next((item for item in items if item.get("evidence_id") == evidence_id), None)
    if selected is None:
        raise ZKError("Evidence ID is not part of this claim")
    if commitment.get("circuit_version") != CIRCUIT_VERSION:
        raise ZKError("Unsupported circuit version")

    artifacts = _artifact_paths()
    missing = [str(path) for path in artifacts.values() if not path.exists()]
    if missing:
        raise ZKError(f"Missing proving artifacts: {', '.join(missing)}")

    # Recompute every leaf from the retained canonical evidence before proving.
    # This prevents a proof over stale stored leaf values after payload tampering.
    digest_parts = []
    for item in items:
        canonical_evidence = item.get("canonical_evidence")
        if not isinstance(canonical_evidence, dict):
            raise ZKError("Committed evidence payload is missing")
        digest = evidence_digest(canonical_evidence)
        if digest["evidence_id"] != item.get("evidence_id") or digest["sha256"] != item.get("sha256"):
            raise ZKError("Stored canonical evidence does not match its evidence ID")
        digest_parts.append({"hi": digest["hi"], "lo": digest["lo"]})

    position = int(selected["position"])
    tree = _run_node("poseidon.mjs", {"digestParts": digest_parts, "index": position})
    if any(tree["leaves"][index] != item.get("leaf") for index, item in enumerate(items)):
        raise ZKError("Stored evidence leaf does not match its canonical payload")
    if tree["root"] != commitment.get("root"):
        raise ZKError("Stored commitment root does not match its evidence leaves")

    circuit_input = {
        "root": commitment["root"],
        "leaf": selected["leaf"],
        "index": position,
        "siblings": tree["siblings"],
    }
    command = [
        os.getenv("ZKRAG_NODE_BINARY", "node"),
        str(_zk_root() / "scripts" / "prove.mjs"),
        str(artifacts["wasm"]),
        str(artifacts["zkey"]),
        str(artifacts["verification_key"]),
    ]
    with _serialized_proof_generation():
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(circuit_input),
                text=True,
                capture_output=True,
                check=False,
                timeout=int(os.getenv("ZKRAG_ZK_TIMEOUT_SECONDS", "120")),
                cwd=str(_zk_root()),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ZKError(f"Proof generation failed: {exc}") from exc
    if completed.returncode != 0:
        raise ZKError(f"Proof generation failed: {(completed.stderr or completed.stdout)[-1000:]}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ZKError("Proof generator returned invalid JSON") from exc
    expected_public = [commitment["root"], selected["leaf"], str(position)]
    if result.get("publicSignals") != expected_public or result.get("verified") is not True:
        raise ZKError("Generated proof public signals do not match the selected evidence")

    selected_digest = evidence_digest(selected["canonical_evidence"])
    package = {
        "package_version": "zkrag-membership-package-v2",
        "circuit_version": CIRCUIT_VERSION,
        "claim_id": record.get("claim_id"),
        "evidence_id": evidence_id,
        "canonical_evidence": selected["canonical_evidence"],
        "evidence_digest": {
            "sha256": selected_digest["sha256"],
            "hi": selected_digest["hi"],
            "lo": selected_digest["lo"],
        },
        "public_inputs": {"root": commitment["root"], "leaf": selected["leaf"], "position": position},
        "public_signals": result["publicSignals"],
        "proof": result["proof"],
        "verification_key_sha256": _sha256_file(artifacts["verification_key"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    package["package_hash"] = _package_hash(package)
    return package


def verify_proof_package(package: Dict[str, Any]) -> bool:
    if package.get("package_version") == INPUT_PACKAGE_VERSION:
        return verify_input_binding_package(package)["verified"]
    artifacts = _artifact_paths()
    verification_key = artifacts["verification_key"]
    if not verification_key.exists():
        raise ZKError(f"Missing verification key: {verification_key}")
    package_version = package.get("package_version")
    if package_version not in {"zkrag-proof-package-v1", "zkrag-membership-package-v2"}:
        return False
    if package.get("circuit_version") != CIRCUIT_VERSION:
        return False
    if not package.get("package_hash") or package["package_hash"] != _package_hash(package):
        return False
    if package.get("verification_key_sha256") != _sha256_file(verification_key):
        return False
    public_inputs = package.get("public_inputs") or {}
    if package_version == "zkrag-membership-package-v2":
        evidence = package.get("canonical_evidence")
        if not isinstance(evidence, dict):
            return False
        digest = evidence_digest(evidence)
        supplied_digest = package.get("evidence_digest") or {}
        if digest["evidence_id"] != package.get("evidence_id"):
            return False
        if any(str(supplied_digest.get(key)) != str(digest[key]) for key in ("sha256", "hi", "lo")):
            return False
        tree = _run_node("poseidon.mjs", {"digestParts": [{"hi": digest["hi"], "lo": digest["lo"]}]})
        if tree["leaves"][0] != str(public_inputs.get("leaf")):
            return False
    expected = [str(public_inputs.get("root")), str(public_inputs.get("leaf")), str(public_inputs.get("position"))]
    if len(package.get("public_signals") or []) != 3 or package.get("public_signals") != expected:
        return False
    result = _run_node("verify.mjs", package, args=[str(verification_key)])
    return result.get("verified") is True


def input_verification_key_sha256() -> str:
    path = _input_artifact_paths()["verification_key"]
    return _sha256_file(path) if path.exists() else ""


def _load_audit_bundle(record: Dict[str, Any]) -> Dict[str, Any]:
    binding = record.get("input_binding") or {}
    metadata = binding.get("audit_bundle") or {}
    path_value = metadata.get("audit_bundle_path")
    if not path_value:
        raise ZKError("input_binding_unavailable_for_legacy_record")
    path = Path(path_value).resolve()
    allowed_root = Path(os.getenv("ZKRAG_AUDIT_DIR", str(Path(__file__).resolve().parent / "zk_audits"))).resolve()
    if allowed_root not in path.parents or not path.is_file():
        raise ZKError("Stored audit bundle is unavailable")
    with path.open("r", encoding="utf-8") as handle:
        bundle = json.load(handle)
    if bundle.get("audit_bundle_hash") != metadata.get("audit_bundle_hash"):
        raise ZKError("Stored audit bundle hash does not match claim metadata")
    return bundle


def _decode_b64(value: Any) -> bytes:
    try:
        return base64.b64decode(str(value), validate=True)
    except Exception as exc:
        raise ZKError("Invalid Base64 data in audit bundle") from exc


def validate_audit_bundle(bundle: Dict[str, Any], *, expected_root: Optional[str] = None) -> Dict[str, Any]:
    """Recompute evidence, PromptBuild, raw-call, request and transcript commitments."""
    checks = {
        "audit_bundle": False,
        "evidence": False,
        "prompt": False,
        "request": False,
        "transcript": False,
        "response": False,
        "record": False,
    }
    if bundle.get("audit_bundle_version") != AUDIT_BUNDLE_VERSION:
        return {"verified": False, "checks": checks}
    supplied_bundle_hash = bundle.get("audit_bundle_hash")
    hashable_bundle = {key: value for key, value in bundle.items() if key != "audit_bundle_hash"}
    if supplied_bundle_hash != sha256_hex(binding_canonical_json(hashable_bundle)):
        return {"verified": False, "checks": checks}
    checks["audit_bundle"] = True

    language = bundle.get("language")
    if language not in {"bn", "en"} or bundle.get("historical_context") != []:
        return {"verified": False, "checks": checks}
    evidence = bundle.get("fresh_evidence") or []
    language_limit = MODEL_CONTEXT_LIMITS[language]
    if not isinstance(evidence, list) or not evidence or len(evidence) > language_limit:
        return {"verified": False, "checks": checks}
    evidence_keys = {"content", "language", "publication_date", "schema_version", "source", "source_type", "title"}
    digest_parts = []
    for item in evidence:
        if (
            not isinstance(item, dict)
            or set(item) != evidence_keys
            or any(not isinstance(value, str) for value in item.values())
            or item.get("schema_version") != SCHEMA_VERSION
            or item.get("language") != language
        ):
            return {"verified": False, "checks": checks}
        digest = evidence_digest(item)
        digest_parts.append({"hi": digest["hi"], "lo": digest["lo"]})
    tree = _run_node("poseidon.mjs", {"digestParts": digest_parts})
    root = str(bundle.get("request_object", {}).get("evidence_root", ""))
    if tree["root"] != root or (expected_root is not None and root != str(expected_root)):
        return {"verified": False, "checks": checks}
    checks["evidence"] = True

    calls = bundle.get("calls") or []
    if not isinstance(calls, list) or not calls:
        return {"verified": False, "checks": checks}
    expected_stages = ["summary", "judge"] if bundle.get("language") == "bn" else ["query", "summary", "judge"]
    expected_templates = [f"{stage}-{'bn' if bundle.get('language') == 'bn' else 'en'}-v2" for stage in expected_stages]
    if [call.get("stage") for call in calls] != expected_stages:
        return {"verified": False, "checks": checks}
    if [call.get("template_version") for call in calls] != expected_templates:
        return {"verified": False, "checks": checks}
    disclosed_templates = bundle.get("templates") or {}
    if bundle.get("template_registry_version") != TEMPLATE_REGISTRY_VERSION:
        return {"verified": False, "checks": checks}
    if disclosed_templates != {version: TEMPLATES[version] for version in expected_templates}:
        return {"verified": False, "checks": checks}
    summary_content = ""
    for call_index, call in enumerate(calls):
        stage = call.get("stage")
        template_version = call.get("template_version")
        upstream = summary_content if stage == "judge" else ""
        stage_evidence = evidence if stage == "summary" else []
        try:
            rebuilt = prompt_build(
                stage=stage,
                normalized_claim=bundle.get("normalized_claim", ""),
                fresh_evidence=stage_evidence,
                historical_context=bundle.get("historical_context") or [],
                template_version=template_version,
                upstream_output=upstream,
            )
        except (TypeError, ValueError):
            return {"verified": False, "checks": checks}
        prompt_bytes = _decode_b64(call.get("prompt_bytes_b64"))
        request_body = _decode_b64(call.get("request_body_b64"))
        response_body = _decode_b64(call.get("response_body_b64"))
        if rebuilt != prompt_bytes or sha256_hex(prompt_bytes) != call.get("stage_prompt_hash"):
            return {"verified": False, "checks": checks}
        if sha256_hex(request_body) != call.get("call_request_body_hash"):
            return {"verified": False, "checks": checks}
        if sha256_hex(response_body) != call.get("call_response_hash"):
            return {"verified": False, "checks": checks}
        try:
            request_json = json.loads(request_body)
            response_json = json.loads(response_body)
            message = request_json["messages"][-1]
            assistant = response_json["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            return {"verified": False, "checks": checks}
        if message.get("role") != "user" or message.get("content", "").encode("utf-8") != rebuilt:
            return {"verified": False, "checks": checks}
        if str(request_json.get("model", "")) != str(call.get("requested_model", "")):
            return {"verified": False, "checks": checks}
        expected_generation = generation_parameters(str(stage))
        if call.get("generation_parameters") != expected_generation:
            return {"verified": False, "checks": checks}
        for key, expected_value in expected_generation.items():
            actual = request_json.get(key)
            normalized_actual = str(actual).lower() if isinstance(actual, bool) else str(actual)
            if normalized_actual != expected_value:
                return {"verified": False, "checks": checks}
        if str(response_json.get("model", "")) != str(call.get("returned_model", "")):
            return {"verified": False, "checks": checks}
        if str(response_json.get("system_fingerprint", "") or "") != str(call.get("system_fingerprint", "")):
            return {"verified": False, "checks": checks}
        if unicodedata.normalize("NFC", assistant) != call.get("assistant_content"):
            return {"verified": False, "checks": checks}
        if stage == "summary":
            summary_content = call.get("assistant_content", "")
    checks["prompt"] = True
    checks["response"] = str(bundle.get("response_hash")) == str(calls[-1].get("call_response_hash"))
    if not checks["response"]:
        return {"verified": False, "checks": checks}

    req = bundle.get("request_object") or {}
    if sha256_hex(binding_canonical_json(req)) != bundle.get("request_hash"):
        return {"verified": False, "checks": checks}
    summary_call = next((item for item in calls if item.get("stage") == "summary"), {})
    if req.get("prompt_hash") != summary_call.get("stage_prompt_hash") or req.get("document_count") != str(len(evidence)):
        return {"verified": False, "checks": checks}
    if req.get("claim_id") != bundle.get("claim_id") or req.get("request_id") != bundle.get("request_id"):
        return {"verified": False, "checks": checks}
    versions = req.get("versions") or {}
    if (
        versions != bundle.get("versions")
        or versions.get("protocol_version") != PROTOCOL_VERSION
        or versions.get("prompt_build_version") != PROMPT_BUILD_VERSION
        or versions.get("template_registry_version") != TEMPLATE_REGISTRY_VERSION
        or versions.get("model_pipeline_version") != MODEL_PIPELINE_VERSION
        or versions.get("circuit_version") != INPUT_CIRCUIT_VERSION
    ):
        return {"verified": False, "checks": checks}
    pipeline = req.get("model_pipeline") or []
    if len(pipeline) != len(calls):
        return {"verified": False, "checks": checks}
    for position, (declared, call) in enumerate(zip(pipeline, calls)):
        if (
            declared.get("position") != str(position)
            or declared.get("stage") != call.get("stage")
            or declared.get("model_id") != call.get("requested_model")
            or declared.get("generation_parameters") != call.get("generation_parameters")
        ):
            return {"verified": False, "checks": checks}
    resolved_models = [
        {
            "stage": call["stage"], "requested_model": call["requested_model"],
            "returned_model": call.get("returned_model", ""),
            "system_fingerprint": call.get("system_fingerprint", ""),
        }
        for call in calls
    ]
    if req.get("resolved_models") != resolved_models:
        return {"verified": False, "checks": checks}
    checks["request"] = True
    checks["transcript"] = _transcript_hash(calls) == bundle.get("transcript_hash")
    if not checks["transcript"]:
        return {"verified": False, "checks": checks}

    record = bundle.get("verification_record") or {}
    checks["record"] = (
        sha256_hex(binding_canonical_json(record)) == bundle.get("verification_record_commitment")
        and record.get("request_hash") == bundle.get("request_hash")
        and record.get("response_hash") == bundle.get("response_hash")
        and record.get("transcript_hash") == bundle.get("transcript_hash")
        and record.get("evidence_root") == root
        and record.get("verdict_text") == bundle.get("verdict_text")
        and record.get("versions") == versions
        and record.get("resolved_models") == resolved_models
    )
    return {"verified": all(checks.values()), "checks": checks, "tree": tree}


def generate_input_binding_proof(record: Dict[str, Any]) -> Dict[str, Any]:
    commitment = record.get("zk_commitment") or {}
    bundle = _load_audit_bundle(record)
    validation = validate_audit_bundle(bundle, expected_root=commitment.get("root"))
    if not validation["verified"]:
        raise ZKError("Stored audit bundle failed independent reconstruction")
    artifacts = _input_artifact_paths()
    missing = [str(path) for path in artifacts.values() if not path.exists()]
    if missing:
        raise ZKError(f"Missing input-binding proving artifacts: {', '.join(missing)}")
    expected_key_hash = _sha256_file(artifacts["verification_key"])
    if bundle.get("verification_record", {}).get("verification_key_sha256") != expected_key_hash:
        raise ZKError("Audit bundle verification-key hash does not match the v2 circuit key")

    evidence = bundle["fresh_evidence"]
    digest_parts = [evidence_digest(item) for item in evidence]
    prompt_limbs = digest_limbs(bundle["prompt_hash"])
    request_limbs = digest_limbs(bundle["request_hash"])
    tree = _run_node("poseidon.mjs", {
        "digestParts": [{"hi": item["hi"], "lo": item["lo"]} for item in digest_parts],
        "promptHashHi": prompt_limbs["hi"],
        "promptHashLo": prompt_limbs["lo"],
        "requestHashHi": request_limbs["hi"],
        "requestHashLo": request_limbs["lo"],
    })
    circuit_input = {
        "root": tree["root"],
        "documentCount": len(evidence),
        "promptHashHi": prompt_limbs["hi"],
        "promptHashLo": prompt_limbs["lo"],
        "requestHashHi": request_limbs["hi"],
        "requestHashLo": request_limbs["lo"],
        "inputBinding": tree["input_binding"],
        "leaves": tree["leaves"] + ["0"] * (16 - len(tree["leaves"])),
    }
    command = [
        os.getenv("ZKRAG_NODE_BINARY", "node"), str(_zk_root() / "scripts" / "prove.mjs"),
        str(artifacts["wasm"]), str(artifacts["zkey"]), str(artifacts["verification_key"]),
    ]
    with _serialized_proof_generation():
        try:
            completed = subprocess.run(
                command, input=json.dumps(circuit_input), text=True, capture_output=True,
                check=False, timeout=int(os.getenv("ZKRAG_ZK_TIMEOUT_SECONDS", "120")), cwd=str(_zk_root()),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ZKError(f"Input-binding proof generation failed: {exc}") from exc
    if completed.returncode != 0:
        raise ZKError(f"Input-binding proof generation failed: {(completed.stderr or completed.stdout)[-1000:]}")
    result = json.loads(completed.stdout)
    expected_public = [
        tree["root"], str(len(evidence)), prompt_limbs["hi"], prompt_limbs["lo"],
        request_limbs["hi"], request_limbs["lo"], tree["input_binding"],
    ]
    if result.get("publicSignals") != expected_public or result.get("verified") is not True:
        raise ZKError("Aggregate proof public signals do not match the audit bundle")
    package = {
        "package_version": INPUT_PACKAGE_VERSION,
        "circuit_version": INPUT_CIRCUIT_VERSION,
        "claim_id": record.get("claim_id"),
        "audit_bundle": bundle,
        "public_inputs": {
            "root": tree["root"], "document_count": len(evidence),
            "prompt_hash_hi": prompt_limbs["hi"], "prompt_hash_lo": prompt_limbs["lo"],
            "request_hash_hi": request_limbs["hi"], "request_hash_lo": request_limbs["lo"],
            "input_binding": tree["input_binding"],
        },
        "public_signals": result["publicSignals"],
        "proof": result["proof"],
        "verification_key_sha256": _sha256_file(artifacts["verification_key"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    package["package_hash"] = _package_hash(package)
    return package


def verify_input_binding_package(package: Dict[str, Any]) -> Dict[str, Any]:
    checks = {"package": False, "audit": False, "public_inputs": False, "proof": False}
    if package.get("package_version") != INPUT_PACKAGE_VERSION or package.get("circuit_version") != INPUT_CIRCUIT_VERSION:
        return {"verified": False, "checks": checks}
    if package.get("package_hash") != _package_hash(package):
        return {"verified": False, "checks": checks}
    checks["package"] = True
    artifacts = _input_artifact_paths()
    verification_key = artifacts["verification_key"]
    if not verification_key.exists():
        raise ZKError(f"Missing verification key: {verification_key}")
    if package.get("verification_key_sha256") != _sha256_file(verification_key):
        return {"verified": False, "checks": checks}
    audit = validate_audit_bundle(package.get("audit_bundle") or {})
    checks["audit"] = audit["verified"]
    if not checks["audit"]:
        return {"verified": False, "checks": checks, "audit_checks": audit["checks"]}
    if package.get("audit_bundle", {}).get("verification_record", {}).get("verification_key_sha256") != package.get("verification_key_sha256"):
        return {"verified": False, "checks": checks}
    bundle = package["audit_bundle"]
    prompt_limbs = digest_limbs(bundle["prompt_hash"])
    request_limbs = digest_limbs(bundle["request_hash"])
    digest_parts = [evidence_digest(item) for item in bundle["fresh_evidence"]]
    rebuilt = _run_node("poseidon.mjs", {
        "digestParts": [{"hi": item["hi"], "lo": item["lo"]} for item in digest_parts],
        "promptHashHi": prompt_limbs["hi"], "promptHashLo": prompt_limbs["lo"],
        "requestHashHi": request_limbs["hi"], "requestHashLo": request_limbs["lo"],
    })
    expected_inputs = {
        "root": rebuilt["root"], "document_count": len(bundle["fresh_evidence"]),
        "prompt_hash_hi": prompt_limbs["hi"], "prompt_hash_lo": prompt_limbs["lo"],
        "request_hash_hi": request_limbs["hi"], "request_hash_lo": request_limbs["lo"],
        "input_binding": rebuilt["input_binding"],
    }
    expected = [
        expected_inputs["root"], str(expected_inputs["document_count"]), expected_inputs["prompt_hash_hi"],
        expected_inputs["prompt_hash_lo"], expected_inputs["request_hash_hi"], expected_inputs["request_hash_lo"],
        expected_inputs["input_binding"],
    ]
    checks["public_inputs"] = package.get("public_inputs") == expected_inputs and package.get("public_signals") == expected
    if not checks["public_inputs"]:
        return {"verified": False, "checks": checks}
    result = _run_node("verify.mjs", package, args=[str(verification_key)])
    checks["proof"] = result.get("verified") is True
    return {"verified": all(checks.values()), "checks": checks, "audit_checks": audit["checks"]}


def proof_storage_dir() -> Path:
    directory = Path(os.getenv("ZKRAG_PROOF_DIR", str(Path(__file__).resolve().parent / "zk_proofs")))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def generate_and_store_proof(storage: Any, claim_id: str, evidence_id: str) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim_id or ""):
        raise ZKError("Invalid claim ID")
    record = storage.get_claim_by_id(claim_id)
    if record is None:
        raise ZKError("Claim not found")
    package = generate_proof(record, evidence_id)

    # Verification is a separate process invocation from proof generation and
    # must pass before either the package or claim status is persisted.
    if not verify_proof_package(package):
        raise ZKError("Generated proof failed independent package verification")

    output_path = proof_storage_dir() / f"{package['package_hash']}.json"
    temporary_path = output_path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(package, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, output_path)

    storage.attach_verified_zk_proof(
        claim_id=claim_id,
        evidence_id=evidence_id,
        proof_metadata={
            "package_hash": package["package_hash"],
            "evidence_id": evidence_id,
            "created_at": package["created_at"],
            "verification_key_sha256": package["verification_key_sha256"],
            "path": str(output_path),
            "status": "membership_verified",
        },
    )
    return package


def generate_and_store_input_binding_proof(storage: Any, claim_id: str) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim_id or ""):
        raise ZKError("Invalid claim ID")
    record = storage.get_claim_by_id(claim_id)
    if record is None:
        raise ZKError("Claim not found")
    package = generate_input_binding_proof(record)
    verification = verify_input_binding_package(package)
    if not verification["verified"]:
        raise ZKError("Generated aggregate proof failed independent package verification")
    output_path = proof_storage_dir() / f"{package['package_hash']}.json"
    temporary_path = output_path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(package, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, output_path)
    storage.attach_verified_input_binding_proof(claim_id, {
        "package_hash": package["package_hash"],
        "created_at": package["created_at"],
        "verification_key_sha256": package["verification_key_sha256"],
        "path": str(output_path),
        "status": "input_binding_verified",
    })
    return package

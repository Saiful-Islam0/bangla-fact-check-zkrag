#!/usr/bin/env python3
"""
Tests for the Most Flagged Sources aggregation feature.

Verifies:
- ClaimStorageManager.get_most_flagged_sources() aggregation & ranking
- Risk level classification logic
- Domain extraction utility
- Sample claims grouping
- On-chain registration tracking
"""

import json
import os
import shutil
import sys
import tempfile

# Ensure the code directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _make_claim(
    claim_id,
    classification="FAKE",
    credibility_score=20,
    submitted_url=None,
    flagged_sources=None,
    onchain=None,
    timestamp="2026-08-18T12:00:00",
    claim_text_original="Test claim",
):
    """Helper to build a minimal claim metadata dict."""
    return {
        "claim_id": claim_id,
        "claim_text": claim_text_original.lower(),
        "claim_text_original": claim_text_original,
        "classification": classification,
        "credibility_score": credibility_score,
        "explanation": "test",
        "evidence_sources": [],
        "warnings": [],
        "language": "bn",
        "timestamp": timestamp,
        "embedding": None,
        "submitted_url": submitted_url,
        "article_text": None,
        "url_snapshot_path": None,
        "flagged_sources": flagged_sources or [],
        "onchain": onchain or {},
    }


def _setup_storage(claims):
    """Write claims into a temp directory and return (storage_dir, manager)."""
    tmp = tempfile.mkdtemp(prefix="test_flagged_sources_")
    for claim in claims:
        path = os.path.join(tmp, f"{claim['claim_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(claim, f, ensure_ascii=False)

    # Import with heavy model stubbed out
    from claim_storage import ClaimStorageManager

    manager = ClaimStorageManager(
        storage_dir=tmp,
        snapshot_dir=os.path.join(tmp, "_snapshots"),
        flagged_sources_dir=os.path.join(tmp, "_flagged"),
    )
    return tmp, manager


def _teardown(tmp):
    shutil.rmtree(tmp, ignore_errors=True)


# ── Test: domain extraction ──────────────────────────────────────

def test_extract_domain():
    print("Testing _extract_domain...")
    from claim_storage import ClaimStorageManager

    assert ClaimStorageManager._extract_domain("https://www.example.com/page") == "example.com"
    assert ClaimStorageManager._extract_domain("http://news.bd.com/article?id=1") == "news.bd.com"
    assert ClaimStorageManager._extract_domain("https://WWW.FOO.org/bar") == "foo.org"
    assert ClaimStorageManager._extract_domain("") is None
    assert ClaimStorageManager._extract_domain(None) is None
    assert ClaimStorageManager._extract_domain("not-a-url") is None
    print("✓ _extract_domain works correctly\n")


# ── Test: basic aggregation & ranking ─────────────────────────────

def test_basic_aggregation():
    print("Testing basic aggregation...")
    claims = [
        _make_claim(
            "c1",
            classification="FAKE",
            credibility_score=15,
            submitted_url="https://badnews.com/article1",
            flagged_sources=[
                {"url": "https://badnews.com/article1", "title": "Bad Article"},
            ],
            timestamp="2026-08-18T10:00:00",
            claim_text_original="ভুয়া খবর ১",
        ),
        _make_claim(
            "c2",
            classification="MISINFORMATION",
            credibility_score=30,
            submitted_url="https://badnews.com/article2",
            flagged_sources=[
                {"url": "https://badnews.com/article2", "title": "Bad Article 2"},
            ],
            timestamp="2026-08-18T11:00:00",
            claim_text_original="ভুয়া খবর ২",
        ),
        _make_claim(
            "c3",
            classification="FAKE",
            credibility_score=10,
            submitted_url="https://otherfake.net/story",
            flagged_sources=[],
            timestamp="2026-08-18T12:00:00",
            claim_text_original="ভুয়া খবর ৩",
        ),
        _make_claim(
            "c4",
            classification="REAL",
            credibility_score=90,
            submitted_url="https://trusted.org/news",
            flagged_sources=[],
            timestamp="2026-08-18T12:00:00",
            claim_text_original="সত্য খবর",
        ),
    ]

    tmp, manager = _setup_storage(claims)
    try:
        results = manager.get_most_flagged_sources(limit=10)

        # badnews.com should have the most flags (flagged_sources entry + submitted_url = 2 flags per claim, 2 claims)
        assert len(results) >= 2, f"Expected at least 2 sources, got {len(results)}"

        # Find badnews.com
        bad = next((r for r in results if r["domain"] == "badnews.com"), None)
        assert bad is not None, "badnews.com not found in results"
        assert bad["total_flags"] >= 2, f"badnews.com should have >= 2 flags, got {bad['total_flags']}"
        assert bad["fake_count"] >= 1, "badnews.com should have >= 1 fake count"
        assert bad["misinfo_count"] >= 1, "badnews.com should have >= 1 misinfo count"
        print(f"  badnews.com: {bad['total_flags']} flags, risk={bad['risk_level']}")

        # otherfake.net should appear (submitted_url for FAKE claim)
        other = next((r for r in results if r["domain"] == "otherfake.net"), None)
        assert other is not None, "otherfake.net not found in results"
        assert other["total_flags"] >= 1
        print(f"  otherfake.net: {other['total_flags']} flags, risk={other['risk_level']}")

        # trusted.org should NOT appear (REAL claim)
        trusted = next((r for r in results if r["domain"] == "trusted.org"), None)
        assert trusted is None, "trusted.org should not appear (REAL classification)"

        # Ranking: badnews.com should be first (more flags)
        assert results[0]["domain"] == "badnews.com", f"Expected badnews.com first, got {results[0]['domain']}"

        print("✓ Basic aggregation works correctly\n")
    finally:
        _teardown(tmp)


# ── Test: risk level classification ────────────────────────────────

def test_risk_levels():
    print("Testing risk level classification...")
    # Create enough flags to hit CRITICAL (>= 5 flags)
    claims = []
    for i in range(6):
        claims.append(
            _make_claim(
                f"critical-{i}",
                classification="FAKE",
                credibility_score=10,
                flagged_sources=[{"url": f"https://spam.com/p{i}"}],
                timestamp=f"2026-08-18T{10+i}:00:00",
                claim_text_original=f"Spam claim {i}",
            )
        )
    # 3 flags for HIGH
    for i in range(3):
        claims.append(
            _make_claim(
                f"high-{i}",
                classification="MISINFORMATION",
                credibility_score=40,
                flagged_sources=[{"url": f"https://suspect.com/p{i}"}],
                timestamp=f"2026-08-18T{10+i}:00:00",
                claim_text_original=f"Suspect claim {i}",
            )
        )
    # 1 flag for MODERATE
    claims.append(
        _make_claim(
            "moderate-0",
            classification="FAKE",
            credibility_score=60,
            flagged_sources=[{"url": "https://meh.com/p0"}],
            timestamp="2026-08-18T10:00:00",
            claim_text_original="Moderate claim",
        )
    )

    tmp, manager = _setup_storage(claims)
    try:
        results = manager.get_most_flagged_sources(limit=10)

        spam = next((r for r in results if r["domain"] == "spam.com"), None)
        assert spam is not None, "spam.com not found"
        assert spam["risk_level"] == "CRITICAL", f"spam.com risk should be CRITICAL, got {spam['risk_level']}"
        print(f"  spam.com: {spam['total_flags']} flags -> {spam['risk_level']}")

        suspect = next((r for r in results if r["domain"] == "suspect.com"), None)
        assert suspect is not None, "suspect.com not found"
        assert suspect["risk_level"] == "HIGH", f"suspect.com risk should be HIGH, got {suspect['risk_level']}"
        print(f"  suspect.com: {suspect['total_flags']} flags -> {suspect['risk_level']}")

        meh = next((r for r in results if r["domain"] == "meh.com"), None)
        assert meh is not None, "meh.com not found"
        assert meh["risk_level"] == "MODERATE", f"meh.com risk should be MODERATE, got {meh['risk_level']}"
        print(f"  meh.com: {meh['total_flags']} flags -> {meh['risk_level']}")

        print("✓ Risk level classification works correctly\n")
    finally:
        _teardown(tmp)


# ── Test: sample claims limited to 3 ──────────────────────────────

def test_sample_claims_limit():
    print("Testing sample claims limit...")
    claims = []
    for i in range(6):
        claims.append(
            _make_claim(
                f"s-{i}",
                classification="FAKE",
                credibility_score=20,
                flagged_sources=[{"url": "https://bigbad.com/page"}],
                timestamp=f"2026-08-18T{10+i}:00:00",
                claim_text_original=f"Claim number {i}",
            )
        )
    tmp, manager = _setup_storage(claims)
    try:
        results = manager.get_most_flagged_sources(limit=5)
        bb = next((r for r in results if r["domain"] == "bigbad.com"), None)
        assert bb is not None, "bigbad.com not found"
        assert len(bb["sample_claims"]) <= 3, f"Expected max 3 sample claims, got {len(bb['sample_claims'])}"
        print(f"  bigbad.com: {len(bb['sample_claims'])} sample claims (max 3)")
        print("✓ Sample claims limit works correctly\n")
    finally:
        _teardown(tmp)


# ── Test: on-chain registration tracking ──────────────────────────

def test_onchain_tracking():
    print("Testing on-chain registration tracking...")
    claims = [
        _make_claim(
            "oc1",
            classification="FAKE",
            credibility_score=15,
            flagged_sources=[{"url": "https://registered.com/bad"}],
            onchain={
                "registration": {"tx_hash": "0xabc123def456"},
            },
            timestamp="2026-08-18T10:00:00",
        ),
        _make_claim(
            "oc2",
            classification="FAKE",
            credibility_score=15,
            flagged_sources=[{"url": "https://notregistered.com/bad"}],
            onchain={},
            timestamp="2026-08-18T10:00:00",
        ),
    ]
    tmp, manager = _setup_storage(claims)
    try:
        results = manager.get_most_flagged_sources(limit=10)
        registered = next((r for r in results if r["domain"] == "registered.com"), None)
        assert registered is not None, "registered.com not found"
        assert registered["onchain_registered"] is True, "registered.com should be on-chain"
        assert registered["onchain_tx_hash"] == "0xabc123def456"
        print(f"  registered.com: onchain={registered['onchain_registered']}, tx={registered['onchain_tx_hash']}")

        not_reg = next((r for r in results if r["domain"] == "notregistered.com"), None)
        assert not_reg is not None, "notregistered.com not found"
        assert not_reg["onchain_registered"] is False, "notregistered.com should not be on-chain"
        print(f"  notregistered.com: onchain={not_reg['onchain_registered']}")

        print("✓ On-chain tracking works correctly\n")
    finally:
        _teardown(tmp)


# ── Test: empty storage ───────────────────────────────────────────

def test_empty_storage():
    print("Testing empty storage...")
    tmp = tempfile.mkdtemp(prefix="test_empty_")
    try:
        from claim_storage import ClaimStorageManager
        manager = ClaimStorageManager(
            storage_dir=tmp,
            snapshot_dir=os.path.join(tmp, "_snapshots"),
            flagged_sources_dir=os.path.join(tmp, "_flagged"),
        )
        results = manager.get_most_flagged_sources()
        assert results == [], f"Expected empty list, got {results}"
        print("✓ Empty storage returns empty list\n")
    finally:
        _teardown(tmp)


# ── Test: min_flags filter ────────────────────────────────────────

def test_min_flags_filter():
    print("Testing min_flags filter...")
    claims = [
        _make_claim(
            "mf1",
            classification="FAKE",
            credibility_score=20,
            flagged_sources=[{"url": "https://single.com/p"}],
            timestamp="2026-08-18T10:00:00",
        ),
        _make_claim(
            "mf2",
            classification="FAKE",
            credibility_score=20,
            flagged_sources=[{"url": "https://double.com/p"}],
            timestamp="2026-08-18T10:00:00",
        ),
        _make_claim(
            "mf3",
            classification="FAKE",
            credibility_score=20,
            flagged_sources=[{"url": "https://double.com/q"}],
            timestamp="2026-08-18T11:00:00",
        ),
    ]
    tmp, manager = _setup_storage(claims)
    try:
        results_min1 = manager.get_most_flagged_sources(min_flags=1)
        results_min2 = manager.get_most_flagged_sources(min_flags=2)

        assert len(results_min1) >= 2, f"min_flags=1 should return >= 2 sources, got {len(results_min1)}"
        assert len(results_min2) >= 1, f"min_flags=2 should return >= 1 source, got {len(results_min2)}"

        # single.com should only appear with min_flags=1
        single_in_min2 = any(r["domain"] == "single.com" for r in results_min2)
        assert not single_in_min2, "single.com should be filtered out with min_flags=2"
        print(f"  min_flags=1: {len(results_min1)} sources")
        print(f"  min_flags=2: {len(results_min2)} sources")
        print("✓ min_flags filter works correctly\n")
    finally:
        _teardown(tmp)


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Most Flagged Sources Feature — Test Suite")
    print("=" * 60 + "\n")

    tests = [
        test_extract_domain,
        test_basic_aggregation,
        test_risk_levels,
        test_sample_claims_limit,
        test_onchain_tracking,
        test_empty_storage,
        test_min_flags_filter,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} FAILED: {e}\n")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
    sys.exit(1 if failed else 0)

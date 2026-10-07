import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import glob
import json as json_lib
import re
import tempfile
import threading


class ClaimStorageManager:
    """Manages persistent storage for verified claims (with optional embeddings)"""

    _metadata_lock = threading.RLock()
    
    def __init__(
        self,
        storage_dir: str = None,
        embedding_model: SentenceTransformer = None,
        snapshot_dir: str = None,
        flagged_sources_dir: str = None,
    ):
        """
        Initialize the claim storage manager
        
        Args:
            storage_dir: Directory to store claim metadata JSON files (defaults to claim_metadata relative to module)
            embedding_model: Optional pre-initialized SentenceTransformer model to reuse
        """
        base_dir = os.path.dirname(__file__)
        if storage_dir is None:
            # Use path relative to module file
            storage_dir = os.path.join(base_dir, "claim_metadata")
        self.storage_dir = storage_dir
        # Create storage directory if it doesn't exist
        os.makedirs(storage_dir, exist_ok=True)

        if snapshot_dir is None:
            snapshot_dir = os.path.join(base_dir, "claim_snapshots")
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)

        if flagged_sources_dir is None:
            flagged_sources_dir = os.path.join(base_dir, "flagged_sources")
        self.flagged_sources_dir = flagged_sources_dir
        os.makedirs(flagged_sources_dir, exist_ok=True)
        
        # Initialize or reuse embedding model
        if embedding_model is not None:
            self.embedding_model = embedding_model
            print("✓ Reusing provided embedding model")
        else:
            try:
                print("Loading SentenceTransformer model for claim embeddings...")
                self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                print("✓ Embedding model loaded successfully")
            except Exception as e:
                print(f"✗ Failed to load embedding model: {e}")
                self.embedding_model = None
    
    def _generate_claim_id(self) -> str:
        """Generate a unique UUID for a new claim"""
        return str(uuid.uuid4())

    def allocate_claim_id(self) -> str:
        """Allocate the stable identifier that must be bound before inference."""
        return self._generate_claim_id()
    
    def _normalize_claim_text(self, text: str) -> str:
        """
        Clean and normalize claim text for comparison
        
        Args:
            text: Raw claim text
            
        Returns:
            Normalized claim text
        """
        if not text:
            return ""
        
        # Lowercase, strip whitespace, remove extra spaces
        normalized = ' '.join(text.lower().strip().split())
        
        return normalized
    
    def compute_claim_embedding(self, claim_text: str) -> Optional[np.ndarray]:
        """
        Generate embedding vector for a claim using SentenceTransformer
        
        Args:
            claim_text: The claim text to embed
            
        Returns:
            Embedding vector as numpy array, or None if model unavailable
        """
        if not self.embedding_model:
            return None
        
        try:
            embedding = self.embedding_model.encode([claim_text])
            return embedding[0]
        except Exception as e:
            print(f"Error computing embedding: {e}")
            return None
    
    def save_claim_record(
        self,
        claim_text: str,
        claim_text_original: str,
        classification: str,
        credibility_score: int,
        explanation: str,
        evidence_sources: List[Dict],
        language: str = 'unknown',
        submitted_url: str = None,
        article_text: str = None,
        url_snapshot_html: str = None,
        flagged_sources: List[Dict] = None,
        onchain_metadata: Optional[Dict] = None,
        zk_commitment: Optional[Dict] = None,
        input_binding: Optional[Dict] = None,
        claim_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Save claim verification results to JSON file
        
        Args:
            claim_text: Normalized claim text
            claim_text_original: Original claim text as submitted
            classification: REAL, FAKE, MISINFORMATION, or UNSURE
            credibility_score: 0-100 credibility score
            explanation: Explanation text
            evidence_sources: List of dicts with url, title, snippet
            language: Language code (e.g., 'en', 'bn', 'hi')
            submitted_url: Optional URL submitted with the claim
            article_text: Optional article text submitted alongside URL
            url_snapshot_html: Raw HTML content of the submitted URL (saved only for FAKE/MISINFORMATION)
            flagged_sources: Optional list of flagged sources dicts (url/title/snippet/similarity/stance/reason)
            onchain_metadata: Optional dict with blockchain registration/lookup info
            zk_commitment: Optional versioned ZK evidence commitment
            
        Returns:
            claim_id if successful, None otherwise
        """
        try:
            claim_id = claim_id or self._generate_claim_id()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim_id):
                raise ValueError("Invalid claim ID")
            normalized_claim = self._normalize_claim_text(claim_text)
            
            # Compute embedding
            embedding = self.compute_claim_embedding(normalized_claim)
            embedding_list = embedding.tolist() if embedding is not None else None
            
            # Create metadata record
            metadata = {
                'claim_id': claim_id,
                'claim_text': normalized_claim,
                'claim_text_original': claim_text_original,
                'classification': classification,
                'credibility_score': credibility_score,
                'explanation': explanation,
                'evidence_sources': evidence_sources,
                'warnings': (onchain_metadata or {}).get('warnings', []) if isinstance(onchain_metadata, dict) else [],
                'language': language,
                'timestamp': datetime.now().isoformat(),
                'embedding': embedding_list,
                'submitted_url': submitted_url,
                'article_text': article_text,
                'url_snapshot_path': None,
                'flagged_sources': flagged_sources or [],
                'onchain': onchain_metadata or {},
                'zk_commitment': zk_commitment,
                'input_binding': input_binding,
            }

            # Save snapshot for flagged claims
            if url_snapshot_html and classification in {'FAKE', 'MISINFORMATION'}:
                snapshot_path = os.path.join(self.snapshot_dir, f"{claim_id}.html")
                with open(snapshot_path, 'w', encoding='utf-8') as f:
                    f.write(url_snapshot_html)
                metadata['url_snapshot_path'] = snapshot_path
            
            # Save to JSON file
            metadata_path = os.path.join(self.storage_dir, f"{claim_id}.json")
            self._save_claim_metadata(metadata, metadata_path)
            
            print(f"Saved claim record: {claim_id}")
            return claim_id
        
        except Exception as e:
            print(f"Error saving claim record: {e}")
            return None
    
    def get_claim_by_id(self, claim_id: str) -> Optional[Dict]:
        """
        Load claim record from JSON file by claim_id
        
        Args:
            claim_id: UUID of the claim
            
        Returns:
            Claim metadata dict, or None if not found
        """
        try:
            metadata_path = os.path.join(self.storage_dir, f"{claim_id}.json")
            if not os.path.exists(metadata_path):
                return None
            
            return self._load_claim_metadata(metadata_path)
        
        except Exception as e:
            print(f"Error loading claim by ID: {e}")
            return None
    
    def get_all_fake_claims(self) -> List[Dict]:
        """
        Return list of all claims classified as FAKE
        
        Returns:
            List of claim metadata dicts
        """
        fake_claims = []
        
        try:
            if not os.path.exists(self.storage_dir):
                return fake_claims
            
            for filename in os.listdir(self.storage_dir):
                if not filename.endswith('.json'):
                    continue
                
                metadata_path = os.path.join(self.storage_dir, filename)
                try:
                    record = self._load_claim_metadata(metadata_path)
                    if record and record.get('classification') == 'FAKE':
                        fake_claims.append(record)
                except Exception as e:
                    print(f"Error reading file {filename}: {e}")
                    continue
        
        except Exception as e:
            print(f"Error retrieving fake claims: {e}")
        
        return fake_claims
    
    def _load_claim_metadata(self, file_path: str) -> Optional[Dict]:
        """
        Read JSON file and return dict
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            Metadata dict, or None on error
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading metadata from {file_path}: {e}")
            return None
    
    def _save_claim_metadata(self, metadata: Dict, file_path: str):
        """
        Write dict to JSON file with proper encoding
        
        Args:
            metadata: Metadata dict to save
            file_path: Path to save JSON file
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving metadata to {file_path}: {e}")
            raise

    def attach_verified_zk_proof(
        self,
        claim_id: str,
        evidence_id: str,
        proof_metadata: Dict,
    ) -> Dict:
        """Atomically attach independently verified proof metadata to a claim."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim_id or ""):
            raise ValueError("Invalid claim ID")
        metadata_path = os.path.join(self.storage_dir, f"{claim_id}.json")

        with self._metadata_lock:
            metadata = self._load_claim_metadata(metadata_path)
            if metadata is None:
                raise FileNotFoundError("Claim not found")
            commitment = metadata.get("zk_commitment")
            if not isinstance(commitment, dict):
                raise ValueError("Claim has no ZK commitment")
            items = commitment.get("items") or []
            selected = next((item for item in items if item.get("evidence_id") == evidence_id), None)
            if selected is None:
                raise ValueError("Evidence ID is not part of this claim")

            selected["proof_status"] = "membership_verified"
            selected["proof_package_hash"] = proof_metadata.get("package_hash")
            proofs = commitment.setdefault("proofs", [])
            proofs[:] = [item for item in proofs if item.get("evidence_id") != evidence_id]
            proofs.append(dict(proof_metadata))
            commitment["status"] = "membership_verified"
            binding = metadata.get("input_binding")
            if isinstance(binding, dict):
                binding["membership_status"] = "membership_verified"
                commitment["input_binding"] = dict(binding)
            self._atomic_write_metadata(metadata_path, metadata)
            return metadata

    def attach_verified_input_binding_proof(self, claim_id: str, proof_metadata: Dict) -> Dict:
        """Atomically mark an aggregate proof verified without changing membership state."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim_id or ""):
            raise ValueError("Invalid claim ID")
        metadata_path = os.path.join(self.storage_dir, f"{claim_id}.json")
        with self._metadata_lock:
            metadata = self._load_claim_metadata(metadata_path)
            if metadata is None:
                raise FileNotFoundError("Claim not found")
            binding = metadata.get("input_binding")
            if not isinstance(binding, dict):
                raise ValueError("Claim has no input-binding commitment")
            binding["status"] = "input_binding_verified"
            binding["aggregate_proof_status"] = "verified"
            binding["aggregate_proof"] = dict(proof_metadata)
            if isinstance(metadata.get("zk_commitment"), dict):
                metadata["zk_commitment"]["input_binding"] = dict(binding)
            self._atomic_write_metadata(metadata_path, metadata)
            return metadata

    def update_anchor_status(self, claim_id: str, anchor: Dict) -> Dict:
        """Atomically attach the bridge result; true means a confirmed receipt only."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim_id or ""):
            raise ValueError("Invalid claim ID")
        metadata_path = os.path.join(self.storage_dir, f"{claim_id}.json")
        with self._metadata_lock:
            metadata = self._load_claim_metadata(metadata_path)
            if metadata is None:
                raise FileNotFoundError("Claim not found")
            binding = metadata.get("input_binding")
            if not isinstance(binding, dict):
                raise ValueError("Claim has no input-binding commitment")
            event = anchor.get("event") or {}
            confirmed = (
                anchor.get("status") == "anchored"
                and str(anchor.get("transaction_hash", "")).startswith("0x")
                and event.get("name") == "VerificationAnchored"
                and event.get("schema_version") == "1"
            )
            binding["anchor"] = dict(anchor)
            binding["anchor_status"] = anchor.get("status", "failed_retryable")
            binding["zk_onchain_anchor"] = confirmed
            if isinstance(metadata.get("zk_commitment"), dict):
                metadata["zk_commitment"]["input_binding"] = dict(binding)
            self._atomic_write_metadata(metadata_path, metadata)
            return metadata

    def _atomic_write_metadata(self, metadata_path: str, metadata: Dict) -> None:
        fd, temp_path = tempfile.mkstemp(prefix=".claim-", suffix=".tmp", dir=self.storage_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, metadata_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def get_trending_claims(
        self, min_count: int = 5, similarity_threshold: float = 0.85
    ) -> List[Dict]:
        """
        Find claims checked multiple times by grouping on embedding similarity.

        Returns groups with >= min_count members, sorted by count desc then
        latest timestamp desc. Each entry uses the most recent claim as
        representative.
        """
        records = []
        try:
            pattern = os.path.join(self.storage_dir, "*.json")
            for path in glob.glob(pattern):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    emb = data.get("embedding")
                    if emb is None:
                        continue
                    records.append({
                        "claim_id": data.get("claim_id"),
                        "claim_text_original": data.get("claim_text_original", ""),
                        "classification": data.get("classification", "UNSURE"),
                        "credibility_score": data.get("credibility_score", 0),
                        "timestamp": data.get("timestamp", ""),
                        "language": data.get("language", "unknown"),
                        "embedding": np.array(emb, dtype=np.float32),
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"Error loading claims for trending: {e}")
            return []

        if len(records) < min_count:
            return []

        embeddings = np.stack([r["embedding"] for r in records])
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normed = embeddings / norms
        sim_matrix = normed @ normed.T

        n = len(records)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= similarity_threshold:
                    union(i, j)

        groups: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        trending = []
        for indices in groups.values():
            if len(indices) < min_count:
                continue
            members = [records[i] for i in indices]
            members.sort(key=lambda m: m["timestamp"], reverse=True)
            rep = members[0]
            trending.append({
                "claim_id": rep["claim_id"],
                "claim_text": rep["claim_text_original"][:180],
                "classification": rep["classification"],
                "credibility_score": rep["credibility_score"],
                "check_count": len(indices),
                "latest_timestamp": rep["timestamp"],
                "language": rep["language"],
            })

        trending.sort(key=lambda t: (t["check_count"], t["latest_timestamp"]), reverse=True)
        return trending

    def get_breaking_feed(self, limit: int = 24) -> List[Dict]:
        """
        Distinct claims for the home carousel: repeated-check clusters first,
        then recent unique claims (no duplicate claim_id). Shapes match trending entries.
        """
        cap = max(5, min(int(limit), 50))
        seen = set()
        out: List[Dict] = []

        try:
            trending = self.get_trending_claims()
        except Exception:
            trending = []

        for t in trending:
            cid = t.get("claim_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append(t)
            if len(out) >= cap:
                return out

        try:
            recent = self.list_recent_claims(limit=max(60, cap * 3))
        except Exception:
            recent = []

        for r in recent:
            cid = r.get("claim_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append({
                "claim_id": cid,
                "claim_text": (r.get("claim_text_original") or "")[:180],
                "classification": r.get("classification") or "UNSURE",
                "credibility_score": r.get("credibility_score", 0),
                "check_count": 1,
                "latest_timestamp": r.get("timestamp") or "",
                "language": r.get("language") or "unknown",
            })
            if len(out) >= cap:
                break

        return out

    def list_recent_claims(self, limit: int = 10) -> List[Dict]:
        """
        Return a list of recent claims sorted by timestamp desc.

        Each entry: {claim_id, classification, claim_text_original, timestamp, language}
        """
        claims = []
        try:
            pattern = os.path.join(self.storage_dir, "*.json")
            files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)[:limit]
            for path in files:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json_lib.load(f)
                        claims.append({
                            "claim_id": data.get("claim_id"),
                            "classification": data.get("classification"),
                            "claim_text_original": data.get("claim_text_original", "")[:180],
                            "timestamp": data.get("timestamp"),
                            "language": data.get("language", "unknown"),
                            "credibility_score": data.get("credibility_score", 0),
                        })
                except Exception as e:
                    print(f"Error reading {path}: {e}")
                    continue
        except Exception as outer:
            print(f"Error listing recent claims: {outer}")
        return claims

    # ------------------------------------------------------------------
    # Most Flagged Sources aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """Extract a clean hostname from a URL string."""
        if not url or not isinstance(url, str):
            return None
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url.strip())
            host = parsed.hostname or ""
            host = host.lower().strip()
            if host.startswith("www."):
                host = host[4:]
            return host if host else None
        except Exception:
            return None

    def get_most_flagged_sources(self, limit: int = 10, min_flags: int = 1) -> List[Dict]:
        """
        Scan all stored claim metadata and aggregate flagged sources by domain.

        Sources come from two places:
        1. ``flagged_sources`` lists inside each claim record.
        2. ``submitted_url`` when the claim is classified FAKE or MISINFORMATION.

        Returns a ranked list (descending by total_flags) of dicts:
            domain, publisher, url, total_flags, fake_count, misinfo_count,
            avg_credibility_score, risk_level, latest_flagged, sample_claims,
            onchain_registered, onchain_tx_hash
        """
        # domain -> aggregation bucket
        buckets: Dict[str, dict] = {}

        def _ensure_bucket(domain: str, sample_url: str) -> dict:
            if domain not in buckets:
                buckets[domain] = {
                    "domain": domain,
                    "publisher": domain,
                    "url": sample_url or "",
                    "total_flags": 0,
                    "fake_count": 0,
                    "misinfo_count": 0,
                    "credibility_scores": [],
                    "latest_flagged": "",
                    "sample_claims": [],
                    "onchain_registered": False,
                    "onchain_tx_hash": None,
                }
            return buckets[domain]

        try:
            pattern = os.path.join(self.storage_dir, "*.json")
            for path in glob.glob(pattern):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue

                claim_id = data.get("claim_id", "")
                claim_text = (data.get("claim_text_original") or "")[:120]
                classification = (data.get("classification") or "UNSURE").upper()
                timestamp = data.get("timestamp", "")
                cred_score = data.get("credibility_score", 0)

                # Compact claim reference
                claim_ref = {
                    "claim_id": claim_id,
                    "claim_text": claim_text,
                    "classification": classification,
                    "timestamp": timestamp,
                }

                # 1) flagged_sources entries
                flagged = data.get("flagged_sources") or []
                if isinstance(flagged, list):
                    for fs in flagged:
                        if not isinstance(fs, dict):
                            continue
                        fs_url = fs.get("url") or ""
                        domain = self._extract_domain(fs_url)
                        if not domain:
                            continue
                        bucket = _ensure_bucket(domain, fs_url)
                        bucket["total_flags"] += 1
                        if classification == "FAKE":
                            bucket["fake_count"] += 1
                        elif classification in ("MISINFORMATION", "MISLEADING"):
                            bucket["misinfo_count"] += 1
                        bucket["credibility_scores"].append(cred_score)
                        if timestamp > bucket["latest_flagged"]:
                            bucket["latest_flagged"] = timestamp
                        # Keep up to 3 sample claims
                        if len(bucket["sample_claims"]) < 3 and claim_id:
                            existing_ids = {c["claim_id"] for c in bucket["sample_claims"]}
                            if claim_id not in existing_ids:
                                bucket["sample_claims"].append(claim_ref)

                # 2) submitted_url when claim is FAKE/MISINFORMATION
                if classification in ("FAKE", "MISINFORMATION", "MISLEADING"):
                    sub_url = data.get("submitted_url") or ""
                    domain = self._extract_domain(sub_url)
                    if domain:
                        bucket = _ensure_bucket(domain, sub_url)
                        bucket["total_flags"] += 1
                        if classification == "FAKE":
                            bucket["fake_count"] += 1
                        else:
                            bucket["misinfo_count"] += 1
                        bucket["credibility_scores"].append(cred_score)
                        if timestamp > bucket["latest_flagged"]:
                            bucket["latest_flagged"] = timestamp
                        if len(bucket["sample_claims"]) < 3 and claim_id:
                            existing_ids = {c["claim_id"] for c in bucket["sample_claims"]}
                            if claim_id not in existing_ids:
                                bucket["sample_claims"].append(claim_ref)

                # 3) Check on-chain registration info
                onchain = data.get("onchain") or {}
                if isinstance(onchain, dict):
                    reg = onchain.get("registration") or {}
                    tx_hash = None
                    if isinstance(reg, dict):
                        for key in ("tx_hash", "transaction_hash", "txHash", "hash"):
                            v = reg.get(key)
                            if isinstance(v, str) and v.strip():
                                tx_hash = v.strip()
                                break
                    if tx_hash:
                        # Mark every domain found in this claim as on-chain registered
                        for fs in (data.get("flagged_sources") or []):
                            if isinstance(fs, dict):
                                d = self._extract_domain(fs.get("url"))
                                if d and d in buckets:
                                    buckets[d]["onchain_registered"] = True
                                    if not buckets[d]["onchain_tx_hash"]:
                                        buckets[d]["onchain_tx_hash"] = tx_hash

        except Exception as e:
            print(f"Error computing most flagged sources: {e}")

        # Build final list
        results = []
        for bucket in buckets.values():
            if bucket["total_flags"] < min_flags:
                continue

            scores = bucket.pop("credibility_scores", [])
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0

            # Risk level
            flags = bucket["total_flags"]
            if avg_score < 25 or flags >= 5:
                risk_level = "CRITICAL"
            elif flags >= 3:
                risk_level = "HIGH"
            else:
                risk_level = "MODERATE"

            bucket["avg_credibility_score"] = avg_score
            bucket["risk_level"] = risk_level

            # Sort sample claims by timestamp desc
            bucket["sample_claims"].sort(
                key=lambda c: c.get("timestamp", ""), reverse=True
            )

            results.append(bucket)

        results.sort(
            key=lambda r: (r["total_flags"], r["latest_flagged"]),
            reverse=True,
        )
        return results[:limit]

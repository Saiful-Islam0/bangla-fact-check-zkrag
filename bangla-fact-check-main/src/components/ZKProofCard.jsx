import { useMemo, useState } from "react";

const STATUS_META = {
  committed_unproven: {
    label: "কমিটমেন্ট প্রস্তুত",
    className:
      "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    icon: "pending",
  },
  membership_verified: {
    label: "মেম্বারশিপ যাচাইকৃত",
    className:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    icon: "verified_user",
  },
  input_binding_verified: {
    label: "মডেল ইনপুট যাচাইকৃত",
    className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    icon: "verified_user",
  },
};

function compactHash(value, head = 16, tail = 12) {
  if (!value) return "—";
  const text = String(value);
  if (text.length <= head + tail + 3) return text;
  return `${text.slice(0, head)}…${text.slice(-tail)}`;
}

function normalizeEvidence(commitment) {
  if (Array.isArray(commitment?.evidence)) return commitment.evidence;
  if (!Array.isArray(commitment?.items)) return [];
  return commitment.items.map((item) => ({
    ...item,
    source: item.source || item.canonical_evidence?.source,
    title: item.title || item.canonical_evidence?.title,
    proof_status: item.proof_status || "unproven",
  }));
}

const CopyButton = ({ value, label, copiedValue, onCopy }) => (
  <button
    type="button"
    onClick={() => onCopy(value, label)}
    className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-[10px] font-semibold text-slate-500 transition-colors hover:border-primary/40 hover:text-primary dark:border-slate-700"
  >
    <span className="material-symbols-outlined text-sm">
      {copiedValue === label ? "check" : "content_copy"}
    </span>
    {copiedValue === label ? "কপি হয়েছে" : "কপি"}
  </button>
);

const ValueBlock = ({ label, value, copyKey, copiedValue, onCopy }) => (
  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/60 min-w-0">
    <div className="mb-1.5 flex items-center justify-between gap-2 min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 truncate">
        {label}
      </p>
      {value && (
        <CopyButton
          value={String(value)}
          label={copyKey}
          copiedValue={copiedValue}
          onCopy={onCopy}
        />
      )}
    </div>
    <p className="break-all font-mono text-xs text-slate-700 dark:text-slate-300">
      {value || "—"}
    </p>
  </div>
);

const ZKProofCard = ({ claimId, commitment, onCommitmentChange }) => {
  const [activeEvidenceId, setActiveEvidenceId] = useState(null);
  const [proofPackage, setProofPackage] = useState(null);
  const [proofError, setProofError] = useState(null);
  const [verificationState, setVerificationState] = useState(null);
  const [copiedValue, setCopiedValue] = useState(null);
  const [aggregateBusy, setAggregateBusy] = useState(false);
  const [anchorBusy, setAnchorBusy] = useState(false);

  const evidence = useMemo(() => normalizeEvidence(commitment), [commitment]);
  const storedProofs = Array.isArray(commitment?.proofs) ? commitment.proofs : [];
  const inputBinding = commitment?.input_binding || null;
  const status = STATUS_META[inputBinding?.status || commitment?.status] || STATUS_META.committed_unproven;

  if (!commitment || !claimId) return null;

  const copyValue = async (value, label) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedValue(label);
      window.setTimeout(() => setCopiedValue(null), 1600);
    } catch {
      setProofError("কপি করা যায়নি। মানটি ম্যানুয়ালি নির্বাচন করুন।");
    }
  };

  const markEvidenceVerified = (evidenceId) => {
    const listKey = Array.isArray(commitment.evidence) ? "evidence" : "items";
    const updated = (commitment[listKey] || []).map((item) =>
      item.evidence_id === evidenceId
        ? { ...item, proof_status: "membership_verified" }
        : item,
    );
    onCommitmentChange?.({
      ...commitment,
      status: "membership_verified",
      [listKey]: updated,
    });
  };

  const generateProof = async (evidenceId) => {
    setActiveEvidenceId(evidenceId);
    setProofPackage(null);
    setProofError(null);
    setVerificationState(null);
    try {
      const response = await fetch("/api/zk/proofs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim_id: claimId, evidence_id: evidenceId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `Proof generation failed (${response.status})`);
      }
      if (!data.verified || !data.proof_package) {
        throw new Error("প্রুফ তৈরি হলেও স্বাধীন যাচাইকরণ সফল হয়নি।");
      }
      setProofPackage(data.proof_package);
      setVerificationState("verified");
      markEvidenceVerified(evidenceId);
    } catch (error) {
      setProofError(error.message || "ZK প্রুফ তৈরি করা যায়নি।");
    } finally {
      setActiveEvidenceId(null);
    }
  };

  const verifyProof = async () => {
    if (!proofPackage) return;
    setVerificationState("verifying");
    setProofError(null);
    try {
      const response = await fetch("/api/zk/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proof_package: proofPackage }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `Proof verification failed (${response.status})`);
      }
      setVerificationState(data.verified ? "verified" : "rejected");
    } catch (error) {
      setVerificationState("rejected");
      setProofError(error.message || "ZK প্রুফ যাচাই করা যায়নি।");
    }
  };

  const generateAggregateProof = async () => {
    setAggregateBusy(true);
    setProofPackage(null);
    setProofError(null);
    try {
      const response = await fetch("/api/zk/input-proofs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim_id: claimId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.verified) throw new Error(data.detail || "Aggregate proof generation failed");
      setProofPackage(data.proof_package);
      setVerificationState("verified");
      onCommitmentChange?.({
        ...commitment,
        input_binding: { ...inputBinding, status: "input_binding_verified", aggregate_proof_status: "verified" },
      });
    } catch (error) {
      setProofError(error.message || "ইনপুট-বাইন্ডিং প্রুফ তৈরি করা যায়নি।");
    } finally { setAggregateBusy(false); }
  };

  const retryAnchor = async () => {
    setAnchorBusy(true);
    setProofError(null);
    try {
      const response = await fetch("/api/zk/anchors", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim_id: claimId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Anchor failed");
      onCommitmentChange?.({
        ...commitment,
        input_binding: { ...inputBinding, anchor_status: data.status, anchor: data, zk_onchain_anchor: data.status === "anchored" },
      });
    } catch (error) { setProofError(error.message || "ব্লকচেইন অ্যাঙ্কর করা যায়নি।"); }
    finally { setAnchorBusy(false); }
  };

  const downloadProof = () => {
    if (!proofPackage) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(proofPackage, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${proofPackage.package_hash || "zkrag-proof"}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="overflow-hidden rounded-xl border border-violet-200 bg-white shadow-sm dark:border-violet-900/70 dark:bg-slate-900 min-w-0">
      <div className="border-b border-violet-100 bg-violet-50/70 p-4 sm:p-5 dark:border-violet-900/50 dark:bg-violet-950/20 min-w-0">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between min-w-0">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
              <span className="material-symbols-outlined">encrypted</span>
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-bold text-slate-900 dark:text-white">
                ZK Evidence & Model-Input Binding
              </h3>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500 dark:text-slate-400 break-words">
                প্রুফটি committed evidence-এর ক্রম এবং SLM-এ পাঠানো exact prompt/request-কে bind করে। এটি উৎসের সত্যতা, retrieval completeness বা AI reasoning-এর correctness প্রমাণ করে না।
              </p>
            </div>
          </div>
          <span className={`inline-flex w-fit items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold shrink-0 ${status.className}`}>
            <span className="material-symbols-outlined text-sm">{status.icon}</span>
            {status.label}
          </span>
        </div>
      </div>

      <div className="space-y-5 p-4 sm:p-5 min-w-0">
        <div className="grid grid-cols-2 gap-2.5 sm:gap-3 sm:grid-cols-4 min-w-0">
          <div className="rounded-lg bg-slate-50 p-2.5 sm:p-3 dark:bg-slate-800/60 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Documents</p>
            <p className="mt-1 text-base sm:text-lg font-black text-slate-800 dark:text-white">
              {commitment.document_count ?? evidence.length}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 p-2.5 sm:p-3 dark:bg-slate-800/60 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Tree capacity</p>
            <p className="mt-1 text-base sm:text-lg font-black text-slate-800 dark:text-white">
              {commitment.tree_capacity ?? "—"}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 p-2.5 sm:p-3 dark:bg-slate-800/60 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Verified</p>
            <p className="mt-1 text-base sm:text-lg font-black text-emerald-600">
              {evidence.filter((item) => item.proof_status === "membership_verified").length}
            </p>
          </div>
          <div className="rounded-lg bg-slate-50 p-2.5 sm:p-3 dark:bg-slate-800/60 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Anchor</p>
            <p className="mt-1 text-xs font-bold text-slate-600 dark:text-slate-300">
              {inputBinding?.zk_onchain_anchor ? "On-chain" : "Local only"}
            </p>
          </div>
        </div>

        <ValueBlock
          label="Merkle root"
          value={commitment.root}
          copyKey="root"
          copiedValue={copiedValue}
          onCopy={copyValue}
        />

        {inputBinding && (
          <div className="space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-3.5 sm:p-4 dark:border-violet-900/60 dark:bg-violet-950/10 min-w-0">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between min-w-0">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-violet-800 dark:text-violet-200">Aggregate model-input proof</p>
                <p className="mt-1 text-[10px] text-slate-500">সব selected evidence একবারে prompt/request commitment-এর সঙ্গে যাচাই করুন</p>
              </div>
              <button type="button" onClick={generateAggregateProof} disabled={aggregateBusy}
                className="w-full sm:w-auto shrink-0 inline-flex items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-bold text-white hover:bg-violet-700 disabled:opacity-60">
                <span className={`material-symbols-outlined text-base ${aggregateBusy ? "animate-spin" : ""}`}>{aggregateBusy ? "progress_activity" : "dataset_linked"}</span>
                {aggregateBusy ? "তৈরি হচ্ছে..." : inputBinding.aggregate_proof_status === "verified" ? "প্রুফ আবার তৈরি করুন" : "Aggregate proof তৈরি করুন"}
              </button>
            </div>
            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 min-w-0">
              {[
                ["Prompt hash", inputBinding.prompt_hash, "prompt-hash"],
                ["Request hash", inputBinding.request_hash, "request-hash"],
                ["Response hash", inputBinding.response_hash, "response-hash"],
                ["Transcript hash", inputBinding.transcript_hash, "transcript-hash"],
                ["Verification record", inputBinding.verification_record_commitment, "record-hash"],
              ].map(([label, value, key]) => <ValueBlock key={key} label={label} value={value} copyKey={key} copiedValue={copiedValue} onCopy={copyValue} />)}
            </div>
            <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-3 text-xs dark:border-slate-700 dark:bg-slate-900 sm:flex-row sm:items-center sm:justify-between min-w-0">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${inputBinding.zk_onchain_anchor || inputBinding.anchor_status === "anchored"
                      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                      : "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                    }`}>
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    Anchor: {inputBinding.anchor_status || "not_configured"}
                  </span>
                  {inputBinding.anchor?.chain_id === "31337" && (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                      Local EVM
                    </span>
                  )}
                  {inputBinding.anchor?.chain_id === "11155111" && (
                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                      Sepolia Testnet
                    </span>
                  )}
                </div>
                {inputBinding.anchor?.transaction_hash && (
                  <p className="mt-1 break-all font-mono text-[10px] text-slate-500 dark:text-slate-400">
                    TX:{" "}
                    {inputBinding.anchor?.chain_id === "11155111" ? (
                      <a
                        href={`https://sepolia.etherscan.io/tx/${inputBinding.anchor.transaction_hash}`}
                        target="_blank"
                        rel="noreferrer"
                        className="underline hover:text-violet-600"
                      >
                        {inputBinding.anchor.transaction_hash}
                      </a>
                    ) : (
                      <span>{inputBinding.anchor.transaction_hash}</span>
                    )}
                  </p>
                )}
                {inputBinding.anchor?.chain_id && (
                  <p className="mt-0.5 break-all font-mono text-[10px] text-slate-500 dark:text-slate-400">
                    Chain: {inputBinding.anchor.chain_id} · Block: {inputBinding.anchor.block_number ?? "—"}
                  </p>
                )}
                {inputBinding.anchor?.contract_address && (
                  <p className="mt-0.5 break-all font-mono text-[10px] text-slate-500 dark:text-slate-400">
                    Contract: {inputBinding.anchor.contract_address}
                  </p>
                )}
              </div>
              <button type="button" onClick={retryAnchor} disabled={anchorBusy || inputBinding.zk_onchain_anchor}
                className="w-full sm:w-auto shrink-0 rounded-lg border border-violet-300 px-3 py-2 text-xs font-bold text-violet-700 disabled:opacity-50 dark:border-violet-800 dark:text-violet-300">
                {anchorBusy ? "Anchoring..." : inputBinding.zk_onchain_anchor ? "Anchored" : "Retry anchor"}
              </button>
            </div>
          </div>
        )}

        <div className="grid gap-3 text-xs grid-cols-1 sm:grid-cols-3 min-w-0">
          <div className="min-w-0">
            <p className="font-bold text-slate-400">Circuit</p>
            <p className="mt-1 break-all font-mono text-slate-700 dark:text-slate-300">{commitment.circuit_version || "—"}</p>
          </div>
          <div className="min-w-0">
            <p className="font-bold text-slate-400">Hash algorithm</p>
            <p className="mt-1 break-all font-mono text-slate-700 dark:text-slate-300">{commitment.hash_algorithm || "—"}</p>
          </div>
          <div className="min-w-0">
            <p className="font-bold text-slate-400">Schema</p>
            <p className="mt-1 break-all font-mono text-slate-700 dark:text-slate-300">{commitment.schema_version || "—"}</p>
          </div>
        </div>

        <div className="flex flex-col gap-1 rounded-lg border border-dashed border-slate-200 px-3 py-2 text-[10px] text-slate-500 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between min-w-0">
          <span className="break-all font-mono">Claim: {claimId}</span>
          <span className="break-all font-mono">
            Anchor status: {inputBinding?.anchor_status || commitment.anchor_status || (commitment.zk_onchain_anchor ? "anchored" : "local_only")}
          </span>
        </div>

        <div className="min-w-0">
          <div className="mb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-1 min-w-0">
            <h4 className="text-sm font-bold text-slate-900 dark:text-white">Committed evidence</h4>
            <span className="text-[10px] text-slate-400">একটি evidence নির্বাচন করে প্রুফ তৈরি করুন</span>
          </div>
          <div className="max-h-[360px] divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-700 min-w-0">
            {evidence.map((item, index) => {
              const isVerified = item.proof_status === "membership_verified";
              const isGenerating = activeEvidenceId === item.evidence_id;
              return (
                <div key={item.evidence_id || index} className="flex flex-col gap-3 p-3 sm:p-4 sm:flex-row sm:items-center sm:justify-between min-w-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-violet-100 text-[10px] font-black text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
                        {(item.position ?? index) + 1}
                      </span>
                      <p className="truncate text-xs font-bold text-slate-800 dark:text-slate-200 min-w-0 flex-1">
                        {item.title || item.source || `Evidence ${index + 1}`}
                      </p>
                    </div>
                    {item.source && (
                      <p className="mt-1.5 truncate pl-8 text-[10px] text-slate-400" title={item.source}>{item.source}</p>
                    )}
                    <p className="mt-1 pl-8 font-mono text-[10px] text-slate-500 break-all" title={item.evidence_id}>
                      {compactHash(item.evidence_id, 22, 14)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => generateProof(item.evidence_id)}
                    disabled={isGenerating || !item.evidence_id}
                    className={`w-full sm:w-auto inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${isVerified
                        ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300"
                        : "bg-violet-600 text-white hover:bg-violet-700"
                      }`}
                  >
                    <span className={`material-symbols-outlined text-base ${isGenerating ? "animate-spin" : ""}`}>
                      {isGenerating ? "progress_activity" : isVerified ? "verified" : "key"}
                    </span>
                    {isGenerating ? "তৈরি হচ্ছে..." : isVerified ? "আবার তৈরি করুন" : "ZK প্রুফ তৈরি করুন"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {proofError && (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300 min-w-0">
            <span className="material-symbols-outlined text-base shrink-0 mt-0.5">error</span>
            <span className="break-words">{proofError}</span>
          </div>
        )}

        {storedProofs.length > 0 && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-3 sm:p-4 dark:border-emerald-900/60 dark:bg-emerald-950/10 min-w-0">
            <p className="mb-3 flex items-center gap-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300">
              <span className="material-symbols-outlined text-base">inventory_2</span>
              সংরক্ষিত যাচাইকৃত প্রুফ ({storedProofs.length})
            </p>
            <div className="space-y-2 min-w-0">
              {storedProofs.map((storedProof, index) => (
                <div key={storedProof.package_hash || index} className="rounded-md bg-white p-3 text-[10px] dark:bg-slate-950/60 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-emerald-600">{storedProof.status || "membership_verified"}</span>
                    {storedProof.created_at && <span className="text-slate-400">{new Date(storedProof.created_at).toLocaleString("bn-BD")}</span>}
                  </div>
                  <p className="mt-1 break-all font-mono text-slate-600 dark:text-slate-300">Package: {storedProof.package_hash || "—"}</p>
                  <p className="mt-1 break-all font-mono text-slate-400">Evidence: {storedProof.evidence_id || "—"}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {proofPackage && (
          <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 sm:p-4 dark:border-emerald-900/60 dark:bg-emerald-950/10 min-w-0">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between min-w-0">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 text-sm font-bold text-emerald-700 dark:text-emerald-300">
                  <span className="material-symbols-outlined text-lg">verified</span>
                  Groth16 proof package
                </p>
                <p className="mt-1 text-[10px] text-slate-500">
                  {proofPackage.package_version === "zkrag-input-binding-package-v2"
                    ? `Full evidence set: ${proofPackage.public_inputs?.document_count ?? "—"} documents`
                    : `Evidence position: ${proofPackage.public_inputs?.position ?? "—"}`}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
                <button
                  type="button"
                  onClick={verifyProof}
                  disabled={verificationState === "verifying"}
                  className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-700 hover:bg-emerald-50 disabled:opacity-60 dark:border-emerald-800 dark:bg-slate-900 dark:text-emerald-300"
                >
                  <span className={`material-symbols-outlined text-base ${verificationState === "verifying" ? "animate-spin" : ""}`}>
                    {verificationState === "verifying" ? "progress_activity" : verificationState === "rejected" ? "dangerous" : "verified_user"}
                  </span>
                  {verificationState === "verifying"
                    ? "যাচাই হচ্ছে..."
                    : verificationState === "rejected"
                      ? "প্রুফ বাতিল"
                      : "স্বাধীনভাবে যাচাইকৃত"}
                </button>
                <button type="button" onClick={downloadProof}
                  className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                  <span className="material-symbols-outlined text-base">download</span>
                  {proofPackage.package_version === "zkrag-input-binding-package-v2" ? "Audit package" : "Proof package"}
                </button>
              </div>
            </div>

            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 min-w-0">
              <ValueBlock
                label="Package hash"
                value={proofPackage.package_hash}
                copyKey="package"
                copiedValue={copiedValue}
                onCopy={copyValue}
              />
              <ValueBlock
                label="Verification key SHA-256"
                value={proofPackage.verification_key_sha256}
                copyKey="vkey"
                copiedValue={copiedValue}
                onCopy={copyValue}
              />
              <ValueBlock
                label={proofPackage.package_version === "zkrag-input-binding-package-v2" ? "Public root" : "Public leaf"}
                value={proofPackage.package_version === "zkrag-input-binding-package-v2" ? proofPackage.public_inputs?.root : proofPackage.public_inputs?.leaf}
                copyKey="leaf"
                copiedValue={copiedValue}
                onCopy={copyValue}
              />
              <ValueBlock
                label={proofPackage.package_version === "zkrag-input-binding-package-v2" ? "Input binding" : "Public position"}
                value={String(proofPackage.package_version === "zkrag-input-binding-package-v2" ? proofPackage.public_inputs?.input_binding ?? "" : proofPackage.public_inputs?.position ?? "")}
                copyKey="position"
                copiedValue={copiedValue}
                onCopy={copyValue}
              />
            </div>

            <details className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-950/60">
              <summary className="cursor-pointer px-3 py-2 text-xs font-bold text-slate-600 dark:text-slate-300">
                Portable proof JSON দেখুন
              </summary>
              <div className="border-t border-slate-200 p-3 dark:border-slate-700">
                <div className="mb-2 flex justify-end">
                  <CopyButton
                    value={JSON.stringify(proofPackage, null, 2)}
                    label="proof-json"
                    copiedValue={copiedValue}
                    onCopy={copyValue}
                  />
                </div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950 p-3 text-[10px] leading-5 text-emerald-300">
                  {JSON.stringify(proofPackage, null, 2)}
                </pre>
              </div>
            </details>
          </div>
        )}
      </div>
    </section>
  );
};

export default ZKProofCard;

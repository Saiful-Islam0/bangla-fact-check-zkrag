import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { buildTxExplorerUrl } from "../utils/blockchainExplorer";

const RISK_STYLE = {
  CRITICAL:
    "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-700",
  HIGH: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700",
  MODERATE:
    "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-600",
};

const CLASS_DOT = {
  FAKE: "bg-red-500",
  MISINFORMATION: "bg-amber-500",
  MISLEADING: "bg-amber-500",
  REAL: "bg-emerald-500",
  UNSURE: "bg-slate-400",
};

function relativeTime(isoString) {
  if (!isoString) return "";
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "এইমাত্র";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function TrustBar({ score }) {
  const pct = Math.max(0, Math.min(100, score));
  const color =
    pct <= 25 ? "bg-red-500" : pct <= 50 ? "bg-amber-500" : pct <= 75 ? "bg-sky-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="h-1.5 flex-1 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 tabular-nums">{pct}</span>
    </div>
  );
}

function StatCard({ icon, label, value, accent = "text-primary" }) {
  return (
    <div className="glass-card p-5 flex flex-col items-center gap-2 min-w-[120px]">
      <span className={`material-symbols-outlined text-2xl ${accent}`}>{icon}</span>
      <p className="text-2xl font-black text-slate-900 dark:text-white tabular-nums">{value}</p>
      <p className="text-[9px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em] text-center">
        {label}
      </p>
    </div>
  );
}

function SourceCard({ source, rank }) {
  const [expanded, setExpanded] = useState(false);
  const riskStyle = RISK_STYLE[source.risk_level] || RISK_STYLE.MODERATE;
  const explorerUrl = source.onchain_tx_hash ? buildTxExplorerUrl(source.onchain_tx_hash) : null;

  const rankBadgeBg =
    rank === 1
      ? "bg-gradient-to-br from-amber-400 to-amber-600 text-white shadow-lg shadow-amber-500/30"
      : rank === 2
        ? "bg-gradient-to-br from-slate-300 to-slate-500 text-white shadow-lg shadow-slate-400/20"
        : rank === 3
          ? "bg-gradient-to-br from-amber-700 to-amber-900 text-amber-100 shadow-lg shadow-amber-800/20"
          : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300";

  return (
    <div className="glass-card p-0 overflow-hidden transition-all duration-300 hover:shadow-xl hover:shadow-primary/5 group">
      {/* Header row */}
      <div className="flex items-center gap-4 px-5 py-4 md:px-6">
        {/* Rank badge */}
        <div
          className={`flex items-center justify-center size-10 rounded-xl font-black text-sm shrink-0 ${rankBadgeBg}`}
        >
          #{rank}
        </div>

        {/* Domain info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="material-symbols-outlined text-red-500 text-lg">language</span>
            <h4 className="font-extrabold text-slate-900 dark:text-white text-sm truncate uppercase tracking-wide">
              {source.domain}
            </h4>
            <span
              className={`text-[8px] font-black uppercase tracking-[0.2em] px-2.5 py-1 rounded-full border ${riskStyle}`}
            >
              {source.risk_level === "CRITICAL"
                ? "🔴 Critical"
                : source.risk_level === "HIGH"
                  ? "🟠 High Risk"
                  : "🟡 Suspicious"}
            </span>
          </div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium truncate mt-0.5">
            {source.url || source.domain}
          </p>
        </div>

        {/* Flags count */}
        <div className="text-right shrink-0 hidden sm:block">
          <p className="text-2xl font-black text-red-600 dark:text-red-400 tabular-nums leading-none">
            {source.total_flags}
          </p>
          <p className="text-[8px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-[0.15em] mt-0.5">
            Flags
          </p>
        </div>
      </div>

      {/* Stats strip */}
      <div className="flex items-center gap-4 px-5 md:px-6 pb-3 flex-wrap">
        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600 dark:text-red-400">
          <span className="size-1.5 rounded-full bg-red-500 inline-block" />
          {source.fake_count} Fake
        </span>
        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-600 dark:text-amber-400">
          <span className="size-1.5 rounded-full bg-amber-500 inline-block" />
          {source.misinfo_count} Misinfo
        </span>
        <div className="flex-1 max-w-[160px]">
          <TrustBar score={source.avg_credibility_score} />
        </div>
        {source.onchain_registered && (
          <a
            href={explorerUrl || "#"}
            target={explorerUrl ? "_blank" : undefined}
            rel={explorerUrl ? "noopener noreferrer" : undefined}
            className="inline-flex items-center gap-1 text-[9px] font-black text-neon-cyan uppercase tracking-widest hover:underline"
          >
            <span className="material-symbols-outlined text-xs">verified</span>
            On-chain
          </a>
        )}
        <span className="text-[9px] font-medium text-slate-400 dark:text-slate-500 ml-auto">
          {relativeTime(source.latest_flagged)}
        </span>
      </div>

      {/* Expandable sample claims */}
      {source.sample_claims && source.sample_claims.length > 0 && (
        <>
          <button
            onClick={() => setExpanded((e) => !e)}
            className="w-full flex items-center justify-between px-5 md:px-6 py-2.5 border-t border-slate-200/80 dark:border-slate-700/60 bg-slate-50/50 dark:bg-slate-800/30 text-[9px] font-black text-primary uppercase tracking-[0.2em] hover:bg-slate-100/70 dark:hover:bg-slate-800/50 transition-colors"
          >
            <span>
              {expanded ? "Hide" : "View"} Related Claims ({source.sample_claims.length})
            </span>
            <span
              className={`material-symbols-outlined text-sm transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}
            >
              expand_more
            </span>
          </button>
          {expanded && (
            <div className="px-5 md:px-6 pb-4 pt-2 space-y-2 bg-slate-50/30 dark:bg-slate-800/20">
              {source.sample_claims.map((claim) => (
                <Link
                  key={claim.claim_id}
                  to={`/claim/${claim.claim_id}`}
                  className="flex items-start gap-2 p-3 rounded-xl border border-slate-200/80 dark:border-slate-700/50 bg-white/60 dark:bg-slate-900/40 hover:border-primary/40 transition-all group/claim"
                >
                  <span
                    className={`size-2 mt-1.5 rounded-full shrink-0 ${CLASS_DOT[claim.classification] || CLASS_DOT.UNSURE}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-slate-700 dark:text-slate-300 line-clamp-2 group-hover/claim:text-primary transition-colors">
                      {claim.claim_text}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[8px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest">
                        {claim.classification}
                      </span>
                      <span className="text-[8px] text-slate-400 dark:text-slate-500">
                        {relativeTime(claim.timestamp)}
                      </span>
                    </div>
                  </div>
                  <span className="material-symbols-outlined text-xs text-slate-400 group-hover/claim:text-primary mt-1 transition-colors shrink-0">
                    arrow_forward
                  </span>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function FlaggedSourcesSection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    setLoading(true);
    fetch("/api/sources/flagged?limit=20")
      .then((r) => (r.ok ? r.json() : { sources: [] }))
      .then((d) => setData(d))
      .catch(() => setData({ sources: [] }))
      .finally(() => setLoading(false));
  }, []);

  const sources = data?.sources || [];
  const filtered = filter
    ? sources.filter(
        (s) =>
          s.domain?.toLowerCase().includes(filter.toLowerCase()) ||
          s.publisher?.toLowerCase().includes(filter.toLowerCase())
      )
    : sources;

  const totalSources = data?.total_sources ?? sources.length;
  const totalFlags = data?.total_flags ?? 0;
  const highRisk = data?.summary?.high_risk_domains ?? 0;
  const onchainTracked = data?.summary?.onchain_tracked ?? 0;

  return (
    <section className="py-20 px-4 md:px-10">
      <div className="max-w-7xl mx-auto">
        {/* Section header */}
        <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
          <h2 className="text-2xl font-black headline-spacing text-primary uppercase flex items-center gap-3">
            <span className="flex items-center justify-center size-10 rounded-xl bg-red-600 text-white shadow-lg shadow-red-600/25">
              <span className="material-symbols-outlined text-[22px]">gpp_bad</span>
            </span>
            <span className="flex flex-col items-start leading-tight">
              <span className="text-xs font-black text-red-700 dark:text-red-400 uppercase tracking-[0.25em]">
                Disinformation Radar
              </span>
              <span className="text-primary">Most Flagged Sources</span>
            </span>
          </h2>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard icon="flag" label="Flagged Sources" value={totalSources} accent="text-red-600" />
          <StatCard icon="gpp_bad" label="High Risk" value={highRisk} accent="text-amber-600" />
          <StatCard icon="warning" label="Total Flags" value={totalFlags} accent="text-red-500" />
          <StatCard icon="verified" label="On-chain Tracked" value={onchainTracked} accent="text-neon-cyan" />
        </div>

        {/* Search/filter bar */}
        <div className="glass-card flex items-center gap-3 px-5 py-3 mb-6">
          <span className="material-symbols-outlined text-slate-400 text-lg">search</span>
          <input
            type="text"
            placeholder="Filter by domain or publisher..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="flex-1 bg-transparent border-none outline-none text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500"
          />
          {filter && (
            <button
              onClick={() => setFilter("")}
              className="text-slate-400 hover:text-red-500 transition-colors"
            >
              <span className="material-symbols-outlined text-sm">close</span>
            </button>
          )}
        </div>

        {/* Source list */}
        {loading ? (
          <div className="glass-card p-12 flex flex-col items-center justify-center gap-3">
            <span className="material-symbols-outlined text-4xl text-primary animate-spin">progress_activity</span>
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">Loading flagged sources...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="glass-card p-12 flex flex-col items-center justify-center gap-3 text-center">
            <span className="material-symbols-outlined text-5xl text-slate-300 dark:text-slate-600">
              shield
            </span>
            <h3 className="text-lg font-bold text-slate-400 dark:text-slate-500">
              {filter ? "No matching sources" : "No flagged sources yet"}
            </h3>
            <p className="text-sm text-slate-400 dark:text-slate-500 max-w-sm">
              {filter
                ? "Try a different search term."
                : "Run fact checks to start populating the disinformation radar."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map((source, i) => (
              <SourceCard key={source.domain} source={source} rank={i + 1} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

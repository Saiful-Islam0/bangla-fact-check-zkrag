#!/usr/bin/env node
import crypto from "node:crypto";

const TEMPLATES = {
  "query-en-v2": "Generate exactly three newline-separated search queries for fact-checking the claim. Cover the main event, named people or organisations, and relevant place or time. Return queries only.",
  "summary-en-v2": "Extract concise factual evidence relevant to the claim. Use only the supplied fresh evidence, identify support or contradiction, and retain source/date references when available.",
  "summary-bn-v2": "সরবরাহ করা নতুন প্রমাণ থেকেই দাবির সঙ্গে সম্পর্কিত ঘটনামূলক তথ্য সংক্ষেপে বের করো। সম্ভব হলে উৎস ও তারিখ উল্লেখ করো।",
  "judge-en-v2": "Classify the claim using only the supplied evidence summary. Respond exactly with Classification: REAL or FAKE or MISINFORMATION or UNSURE, Credibility Score: 0-100 (or N/A for UNSURE), and Explanation.",
  "judge-bn-v2": "শুধু সরবরাহ করা প্রমাণের সারসংক্ষেপ ব্যবহার করে দাবিকে REAL, FAKE, MISINFORMATION অথবা UNSURE হিসেবে শ্রেণিবদ্ধ করো। ঠিক এই বিন্যাসে উত্তর দাও: Classification, Credibility Score, Explanation। ব্যাখ্যা বাংলায় লিখবে।",
};
function norm(value) {
  if (typeof value === "string") return value.normalize("NFC");
  if (Array.isArray(value)) return value.map(norm);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map(key => [key, norm(value[key])]));
  return value;
}
const canonical = value => Buffer.from(JSON.stringify(norm(value)), "utf8");
const field = (name, value) => { const body = Buffer.isBuffer(value) ? value : Buffer.from(value, "utf8"); return Buffer.concat([Buffer.from(`${name}:${body.length}\n`), body, Buffer.from("\n")]); };
let text = ""; for await (const chunk of process.stdin) text += chunk;
const data = JSON.parse(text || "{}");
const fresh = (data.fresh_evidence || []).map(canonical), history = (data.historical_context || []).map(canonical);
const parts = [Buffer.from("ZKRAG-PROMPT-BUILD/2\n"), field("prompt_build_version", "zkrag-prompt-build-v2"), field("stage", data.stage), field("template_version", data.template_version), field("instruction", TEMPLATES[data.template_version]), field("normalized_claim", data.normalized_claim.normalize("NFC")), field("fresh_evidence_count", String(fresh.length))];
fresh.forEach((item, i) => parts.push(field(`fresh_evidence_${i}`, item)));
parts.push(field("historical_context_count", String(history.length)));
history.forEach((item, i) => parts.push(field(`historical_context_${i}`, item)));
parts.push(field("upstream_output", (data.upstream_output || "").normalize("NFC")));
const output = Buffer.concat(parts);
process.stdout.write(JSON.stringify({ base64: output.toString("base64"), sha256: crypto.createHash("sha256").update(output).digest("hex") }) + "\n");

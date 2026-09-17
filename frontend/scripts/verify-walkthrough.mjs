import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";

const manifestPath = new URL("../public/walkthrough/manifest.json", import.meta.url);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const policy = manifest.policy;
const caseIds = manifest.caseIds;
if (!policy || !Array.isArray(caseIds) || new Set(caseIds).size !== caseIds.length) {
  throw new Error("The walkthrough manifest lacks a valid ordered case list or showcase policy.");
}
for (const directory of [
  new URL("../public/walkthrough/", import.meta.url),
  new URL("../public/walkthrough/cases/", import.meta.url),
  new URL("../public/walkthrough/runs/", import.meta.url),
]) {
  const unexpected = (await readdir(directory)).filter((name) => / \d+\.json$/i.test(name));
  if (unexpected.length) throw new Error(`Walkthrough contains accidental conflict copies: ${unexpected.join(", ")}`);
}

if (
  !Number.isInteger(manifest.caseCount) ||
  manifest.caseCount !== policy.caseCount ||
  manifest.recordedCaseCount !== manifest.caseCount
) {
  throw new Error(
    "The Vercel walkthrough is incomplete. Run ./run-verinice --record-walkthrough " +
      "from the VeriNICE project root before deploying.",
  );
}

const recordedCaseIds = Object.keys(manifest.runDigests ?? {});
if (recordedCaseIds.length !== manifest.caseCount) {
  throw new Error("The walkthrough manifest does not enumerate every recorded case.");
}
if (caseIds.length !== manifest.caseCount || caseIds.some((id) => !recordedCaseIds.includes(id))) {
  throw new Error("The recorded walkthrough case set does not match the source manifest.");
}

const categoryCounts = new Map();
const verdictCounts = new Map();
let averitecCount = 0;

for (const caseId of caseIds) {
  const caseUrl = new URL(`../public/walkthrough/cases/${caseId}.json`, import.meta.url);
  const demoCase = JSON.parse(await readFile(caseUrl, "utf8"));
  if (!demoCase.origin || !demoCase.category || !demoCase.demoFocus) {
    throw new Error(`Walkthrough ${caseId} lacks showcase origin or category metadata.`);
  }
  if (demoCase.origin === "AVERITEC") averitecCount += 1;
  else categoryCounts.set(demoCase.category, (categoryCounts.get(demoCase.category) ?? 0) + 1);
  verdictCounts.set(demoCase.label, (verdictCounts.get(demoCase.label) ?? 0) + 1);
  if (demoCase.origin === "CONSTRUCTED") {
    if (demoCase.documents.length !== policy.constructedSourcesPerCase) {
      throw new Error(`Constructed walkthrough ${caseId} source count does not match policy.`);
    }
    for (const document of demoCase.documents) {
      const excerptWords = document.text.trim().split(/\s+/).length;
      const excerptHash = createHash("sha256").update(document.text, "utf8").digest("hex");
      if (
        document.sourceType !== "SOURCE_EXCERPT"
        || excerptWords < policy.excerptWords.minimum
        || excerptWords > policy.excerptWords.maximum
        || !document.publisher
        || !document.retrievedAt
        || !document.sourceDescriptor
        || !document.excerptRationale
        || excerptHash !== document.excerptSha256
      ) {
        throw new Error(`Constructed walkthrough ${caseId} has invalid source details.`);
      }
    }
  }
  const sourceKeys = demoCase.documents.map((document) => {
    const url = new URL(document.url);
    url.protocol = "https:";
    const query = [...url.searchParams.entries()].sort(([leftKey, leftValue], [rightKey, rightValue]) =>
      leftKey.localeCompare(rightKey) || leftValue.localeCompare(rightValue));
    url.hash = "";
    url.search = new URLSearchParams(query).toString();
    return url.toString();
  });
  if (new Set(sourceKeys).size !== sourceKeys.length) {
    throw new Error(`Walkthrough ${caseId} contains duplicate canonical sources.`);
  }
  const runUrl = new URL(`../public/walkthrough/runs/${caseId}.json`, import.meta.url);
  const run = JSON.parse(await readFile(runUrl, "utf8"));
  const serialized = JSON.stringify(run).toLowerCase();
  if (
    run.schemaVersion !== 7
    || !run.assessment
    || !run.reasoning
    || run.verdict?.aggregationSchemaVersion !== 3
    || run.recordedWith?.pipelineRevision !== "generalized-symbolic-v6"
    || !["HYBRID", "SEMANTIC", "LEXICAL"].includes(run.recordedWith?.retrievalMethod)
    || !/^[a-f0-9]{64}$/.test(run.recordedWith?.inputDigest ?? "")
    || "claimPosition" in run.assessment
    || run.assessment.obligations?.some((item) => !Array.isArray(item.scopeChecks))
    || run.classifications
    || run.evidenceAudit
    || run.recordedWith?.nliModel
    || run.recordedWith?.linguisticsModel
    || run.linguistics
    || serialized.includes("spacy")
    || serialized.includes("deberta")
  ) {
    throw new Error(
      `Walkthrough ${caseId} uses a stale pipeline schema. Re-record all cases before deploying.`,
    );
  }
  if (run.reasoning.some((item) => item.program?.version !== 1 || !Array.isArray(item.program?.steps))) {
    throw new Error(`Walkthrough ${caseId} is missing typed symbolic programs.`);
  }
  if (run.verdict?.verdict !== demoCase.label) {
    throw new Error(`Walkthrough ${caseId} does not match its approved reference label.`);
  }
  const forbiddenWarnings = new Set(["DECOMPOSITION_FALLBACK", "MISSING_ASSERTION", "UNDER_DECOMPOSED"]);
  if (run.warnings?.some((warning) => forbiddenWarnings.has(warning.code))) {
    throw new Error(`Walkthrough ${caseId} contains a decomposition fallback or coverage warning.`);
  }
  if (run.assessment.obligations.some((item) => {
    const missing = String(item.missingInformation ?? "").trim().toLowerCase();
    return ["false", "null", "none"].includes(missing) || (missing && !/[.!?]$/.test(missing));
  })) {
    throw new Error(`Walkthrough ${caseId} contains invalid missing-information copy.`);
  }
  const audits = new Map(run.assessment.obligations.map((item) => [item.atomId, item]));
  for (const audit of run.assessment.obligations) {
    const mismatched = new Set(audit.scopeChecks.filter((check) => check.status === "MISMATCH").map((check) => check.spanId));
    if ([...audit.supportSpanIds, ...audit.refuteSpanIds].some((spanId) => mismatched.has(spanId))) {
      throw new Error(`Walkthrough ${caseId} selects a jurisdiction-mismatched candidate.`);
    }
  }
  for (const obligation of run.verdict.obligations) {
    if (audits.get(obligation.obligationId)?.sufficiency === "SUFFICIENT") continue;
    const decisive = [...obligation.supportEdgeIds, ...obligation.refuteEdgeIds]
      .some((edge) => edge.includes(":evidence:") || edge.includes(":inference:bundle:"));
    if (decisive) throw new Error(`Walkthrough ${caseId} promotes insufficient assessed evidence.`);
  }
}

const displayedCounts = new Map(categoryCounts);
displayedCounts.set("AVERITEC", averitecCount);
if (
  !Array.isArray(policy.displayedCategories)
  || new Set(policy.displayedCategories).size !== policy.displayedCategories.length
  || displayedCounts.size !== policy.displayedCategories.length
  || policy.displayedCategories.some(
    (category) => displayedCounts.get(category) !== policy.casesPerDisplayedCategory
  )
) {
  throw new Error("Walkthrough displayed category counts do not match showcase policy.");
}
if (
  !policy.verdictCounts
  || Object.keys(policy.verdictCounts).length !== verdictCounts.size
  || Object.entries(policy.verdictCounts).some(([label, count]) => verdictCounts.get(label) !== count)
) {
  throw new Error("Walkthrough verdict distribution does not match showcase policy.");
}

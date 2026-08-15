import { readFile } from "node:fs/promises";

const manifestPath = new URL("../public/walkthrough/manifest.json", import.meta.url);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

if (
  !Number.isInteger(manifest.caseCount) ||
  manifest.caseCount < 1 ||
  manifest.recordedCaseCount !== manifest.caseCount
) {
  throw new Error(
    "The Vercel walkthrough is incomplete. Run ./run-verigraph --record-walkthrough " +
      "from the VeriGraph root before deploying.",
  );
}

export type DeploymentMode = "live" | "walkthrough";

// This is intentionally a build-time public value. Vercel builds the
// walkthrough mode without a backend URL, while Docker Compose builds live mode.
export const deploymentMode: DeploymentMode =
  process.env.NEXT_PUBLIC_VERIGRAPH_MODE === "walkthrough" ? "walkthrough" : "live";

export const isWalkthroughMode = deploymentMode === "walkthrough";

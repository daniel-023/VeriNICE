import { Suspense } from "react";
import { VeriGraphApp } from "@/components/VeriGraphApp";

export default function WalkthroughPage() {
  return (
    <Suspense fallback={<main className="route-loading">Loading VeriTrace…</main>}>
      <VeriGraphApp mode="walkthrough" />
    </Suspense>
  );
}

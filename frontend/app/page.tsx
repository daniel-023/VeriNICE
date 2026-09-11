import { Suspense } from "react";
import { VeriGraphApp } from "@/components/VeriGraphApp";

export default function HomePage() {
  return (
    <Suspense fallback={<main className="route-loading">Loading VeriNICE…</main>}>
      <VeriGraphApp />
    </Suspense>
  );
}

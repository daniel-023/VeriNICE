import { Suspense } from "react";
import { VeriGraphApp } from "@/components/VeriGraphApp";

export default function HomePage() {
  return (
    <Suspense fallback={<main className="route-loading">Loading VeriTrace…</main>}>
      <VeriGraphApp />
    </Suspense>
  );
}

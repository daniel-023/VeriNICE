import { Suspense } from "react";
import { VeriNICEApp } from "@/components/VeriNICEApp";

export default function HomePage() {
  return (
    <Suspense fallback={<main className="route-loading">Loading VeriNICE…</main>}>
      <VeriNICEApp />
    </Suspense>
  );
}

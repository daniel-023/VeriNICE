import { Suspense } from "react";
import { VeriNICEApp } from "@/components/VeriNICEApp";

export default function WalkthroughPage() {
  return (
    <Suspense fallback={<main className="route-loading">Loading VeriNICE…</main>}>
      <VeriNICEApp mode="walkthrough" />
    </Suspense>
  );
}

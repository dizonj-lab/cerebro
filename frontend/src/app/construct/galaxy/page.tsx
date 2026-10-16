import type { Metadata } from "next";
import { Suspense } from "react";

import { GalaxyView } from "@/components/galaxy/GalaxyView";

export const metadata: Metadata = { title: "Knowledge Galaxy" };

export default function GalaxyPage() {
  // The view reads ?focus from the URL on the client, so it suspends.
  return (
    <Suspense fallback={<p className="p-4 text-sm text-white/50">Loading galaxy…</p>}>
      <GalaxyView />
    </Suspense>
  );
}

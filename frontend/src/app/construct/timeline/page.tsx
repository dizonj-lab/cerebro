import type { Metadata } from "next";
import { Suspense } from "react";

import { TimelineView } from "@/components/timeline/TimelineView";

export const metadata: Metadata = { title: "Timeline" };
export const dynamic = "force-dynamic";

export default function TimelinePage() {
  // The view reads ?focus from the URL on the client, so it suspends.
  return (
    <Suspense fallback={<p className="p-4 text-sm text-scene-ink/50">Loading timeline…</p>}>
      <TimelineView />
    </Suspense>
  );
}

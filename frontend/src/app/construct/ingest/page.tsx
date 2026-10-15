import type { Metadata } from "next";

import { IngestView } from "./IngestView";

export const metadata: Metadata = { title: "Ingest" };
export const dynamic = "force-dynamic";

export default function IngestPage() {
  return <IngestView />;
}

import type { Metadata } from "next";

import { PerformanceReport } from "./PerformanceReport";

export const metadata: Metadata = { title: "Performance" };
export const dynamic = "force-dynamic";

export default function PerformancePage() {
  return <PerformanceReport />;
}

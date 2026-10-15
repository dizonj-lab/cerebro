import type { Metadata } from "next";

import { GalaxyView } from "@/components/galaxy/GalaxyView";

export const metadata: Metadata = { title: "Knowledge Galaxy" };

export default function GalaxyPage() {
  return <GalaxyView />;
}

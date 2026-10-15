import type { Metadata } from "next";

import { LibraryView } from "./LibraryView";

export const metadata: Metadata = { title: "Library" };
export const dynamic = "force-dynamic";

export default function LibraryPage() {
  return <LibraryView />;
}

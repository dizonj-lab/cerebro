import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/construct/PageHeader";
import { SearchView } from "@/components/search/SearchView";

export const metadata: Metadata = { title: "Search" };
export const dynamic = "force-dynamic";

export default function SearchPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Search"
        description="Across your documents and the knowledge registered from them."
      />
      {/* The query is read from the URL on the client, so the view suspends. */}
      <Suspense fallback={<p className="text-sm text-ink-muted">Loading search...</p>}>
        <SearchView />
      </Suspense>
    </div>
  );
}

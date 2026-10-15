import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ConstructShell } from "@/app/construct/ConstructShell";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = { title: "The Construct" };

// Session state is per-request; never statically rendered or cached.
export const dynamic = "force-dynamic";

export default async function ConstructLayout({ children }: { children: React.ReactNode }) {
  // Authoritative check: the token is validated against the API, not merely
  // present. Middleware has already handled the cheap case.
  const user = await getCurrentUser();
  if (!user) redirect("/login?next=/construct");

  return <ConstructShell user={user}>{children}</ConstructShell>;
}

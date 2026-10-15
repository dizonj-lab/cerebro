import type { Metadata } from "next";

import { SettingsView } from "./SettingsView";

export const metadata: Metadata = { title: "Settings" };
export const dynamic = "force-dynamic";

export default function SettingsPage() {
  return <SettingsView />;
}

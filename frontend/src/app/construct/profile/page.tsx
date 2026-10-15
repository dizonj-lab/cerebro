import type { Metadata } from "next";

import { ProfileForm } from "./ProfileForm";

export const metadata: Metadata = { title: "Profile" };
export const dynamic = "force-dynamic";

export default function ProfilePage() {
  return <ProfileForm />;
}

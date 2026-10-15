import type { Metadata } from "next";

import { SignupForm } from "./SignupForm";

export const metadata: Metadata = { title: "Create Account" };

export default function SignupPage() {
  return <SignupForm />;
}

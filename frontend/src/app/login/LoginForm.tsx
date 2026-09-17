"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import { ApiError, api } from "@/lib/api";

function LoginFormInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [submitting, setSubmitting] = useState(false);

  // Only ever an internal path: an absolute URL here would be an open redirect.
  const nextParam = searchParams.get("next");
  const redirectTo = nextParam?.startsWith("/") && !nextParam.startsWith("//")
    ? nextParam
    : "/construct";

  function validate() {
    const errors: { email?: string; password?: string } = {};
    if (!email.trim()) errors.email = "Email is required";
    if (!password) errors.password = "Password is required";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await api.login({ email: email.trim(), password });
      // Full navigation so middleware and the server layout observe the
      // freshly set cookie.
      router.replace(redirectTo);
      router.refresh();
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : "Unable to sign in. Please try again.",
      );
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Sign in"
      subtitle="Continue to your Digital Knowledge Twin."
      footer={
        <p>
          New to CEREBRO?{" "}
          <Link href="/signup" className="font-medium text-accent hover:underline">
            Create Account
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <ErrorMessage>{formError}</ErrorMessage>

        <FormField htmlFor="email" label="Email" error={fieldErrors.email}>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            autoFocus
            value={email}
            invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <FormField htmlFor="password" label="Password" error={fieldErrors.password}>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            invalid={Boolean(fieldErrors.password)}
            aria-describedby={fieldErrors.password ? "password-error" : undefined}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <Button type="submit" fullWidth size="lg" loading={submitting} className="mt-1">
          {submitting ? "Signing in" : "Sign In"}
        </Button>
      </form>
    </AuthShell>
  );
}

export function LoginForm() {
  return (
    <Suspense fallback={null}>
      <LoginFormInner />
    </Suspense>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import { ApiError, api } from "@/lib/api";

const PASSWORD_MIN_LENGTH = 10;
// Mirrors the backend rule; the server remains the authority.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FieldErrors {
  displayName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

export function SignupForm() {
  const router = useRouter();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const errors: FieldErrors = {};

    if (!displayName.trim()) {
      errors.displayName = "Display name is required";
    } else if (displayName.trim().length > 100) {
      errors.displayName = "Display name must be 100 characters or fewer";
    }

    if (!email.trim()) {
      errors.email = "Email is required";
    } else if (!EMAIL_PATTERN.test(email.trim())) {
      errors.email = "Enter a valid email address";
    }

    if (!password) {
      errors.password = "Password is required";
    } else if (password.length < PASSWORD_MIN_LENGTH) {
      errors.password = `Password must be at least ${PASSWORD_MIN_LENGTH} characters`;
    } else if (!/[a-zA-Z]/.test(password) || !/\d/.test(password)) {
      errors.password = "Password must contain at least one letter and one number";
    }

    if (!confirmPassword) {
      errors.confirmPassword = "Confirm your password";
    } else if (password !== confirmPassword) {
      errors.confirmPassword = "Passwords do not match";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await api.signup({
        display_name: displayName.trim(),
        email: email.trim(),
        password,
      });
      // Signup establishes a session, so the new account lands straight in
      // The Construct.
      router.replace("/construct");
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setFieldErrors((prev) => ({ ...prev, email: error.message }));
      } else {
        setFormError(
          error instanceof ApiError
            ? error.message
            : "Unable to create your account. Please try again.",
        );
      }
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Begin building your knowledge twin."
      footer={
        <p>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign In
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <ErrorMessage>{formError}</ErrorMessage>

        <FormField htmlFor="displayName" label="Display Name" error={fieldErrors.displayName}>
          <Input
            id="displayName"
            name="displayName"
            autoComplete="name"
            autoFocus
            value={displayName}
            invalid={Boolean(fieldErrors.displayName)}
            aria-describedby={fieldErrors.displayName ? "displayName-error" : undefined}
            onChange={(e) => setDisplayName(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <FormField htmlFor="email" label="Email" error={fieldErrors.email}>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <FormField
          htmlFor="password"
          label="Password"
          error={fieldErrors.password}
          hint={`At least ${PASSWORD_MIN_LENGTH} characters, including a letter and a number.`}
        >
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            value={password}
            invalid={Boolean(fieldErrors.password)}
            aria-describedby={
              fieldErrors.password ? "password-error" : "password-hint"
            }
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <FormField
          htmlFor="confirmPassword"
          label="Confirm Password"
          error={fieldErrors.confirmPassword}
        >
          <Input
            id="confirmPassword"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            invalid={Boolean(fieldErrors.confirmPassword)}
            aria-describedby={
              fieldErrors.confirmPassword ? "confirmPassword-error" : undefined
            }
            onChange={(e) => setConfirmPassword(e.target.value)}
            disabled={submitting}
          />
        </FormField>

        <Button type="submit" fullWidth size="lg" loading={submitting} className="mt-1">
          {submitting ? "Creating account" : "Create Account"}
        </Button>
      </form>
    </AuthShell>
  );
}

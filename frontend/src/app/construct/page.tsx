import { getCurrentUser } from "@/lib/session";

export default async function ConstructPage() {
  const user = await getCurrentUser();

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Welcome to CEREBRO</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        Your knowledge twin begins here.
      </p>

      {user && (
        <p className="mt-8 border-t border-line pt-6 text-sm text-ink-subtle">
          Signed in as {user.display_name}.
        </p>
      )}
    </div>
  );
}

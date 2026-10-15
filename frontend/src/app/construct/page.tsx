import { DashboardView } from "@/components/dashboard/DashboardView";
import { getCurrentProfile, getCurrentUser } from "@/lib/session";

/**
 * The dashboard.
 *
 * Identity is resolved on the server from the existing session, so the name
 * in the greeting is never guessed or passed in from the client. Everything
 * else arrives from one `/api/dashboard` call made by the view.
 */
export default async function ConstructPage() {
  const [user, profile] = await Promise.all([getCurrentUser(), getCurrentProfile()]);
  const firstName =
    profile?.full_name?.trim().split(/\s+/)[0] ||
    user?.display_name?.trim().split(/\s+/)[0] ||
    "there";

  // Kept from the previous dashboard: both predate this design and are
  // working features, so they are preserved rather than dropped for a
  // cosmetic match. Neither shows anything once there is nothing to say.
  const focus = [...(profile?.current_topics ?? []), ...(profile?.expertise ?? [])].slice(0, 3);

  return (
    <DashboardView
      firstName={firstName}
      focus={focus}
      profile={
        profile && profile.completion_percent < 100
          ? {
              percent: profile.completion_percent,
              completed: profile.completed_fields,
              total: profile.total_fields,
            }
          : null
      }
    />
  );
}

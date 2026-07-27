import { createClient } from "@/lib/supabase/server";
import type { Profile } from "@/lib/types";

/**
 * The signed-in user's profile, or null.
 *
 * The role decides what the UI offers, but never what it can reach: RLS is what actually
 * enforces access. Hiding a button the database would refuse anyway is courtesy, not
 * security — the two must agree, and when they disagree the database wins.
 */
export async function getProfile(): Promise<Profile | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data } = await supabase
    .from("profiles")
    .select("id, full_name, role, active")
    .eq("id", user.id)
    .single<Profile>();

  return data ?? null;
}

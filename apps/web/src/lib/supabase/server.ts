import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * Server-component client. Still the publishable key, never the secret one: server components
 * act on behalf of the signed-in user, so their queries must go through RLS exactly like the
 * browser's. The secret key lives only in services/api.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component, where cookies are read-only. The middleware
            // refreshes the session instead, so this is safe to ignore.
          }
        },
      },
    },
  );
}

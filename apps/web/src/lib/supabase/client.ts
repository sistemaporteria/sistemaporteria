import { createBrowserClient } from "@supabase/ssr";

/**
 * Browser client. Uses the publishable key, which is public by design: it ships inside the
 * JavaScript bundle. What protects the data is RLS, not the secrecy of this key.
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
}

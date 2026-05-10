/**
 * GET /api/votes — return current vote counts for all posts.
 * Cached 60s edge-side; clients also cache locally.
 */

interface Env {
  FRONTLINE_VOTES: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async ({ env }) => {
  if (!env.FRONTLINE_VOTES) {
    return new Response(
      JSON.stringify({ counts: {}, configured: false }),
      { headers: { "Content-Type": "application/json" } },
    );
  }

  const counts: Record<string, number> = {};
  let cursor: string | undefined;
  do {
    const list = await env.FRONTLINE_VOTES.list({ prefix: "count:", cursor });
    for (const key of list.keys) {
      const postId = key.name.slice("count:".length);
      const value = await env.FRONTLINE_VOTES.get(key.name);
      counts[postId] = parseInt(value || "0", 10);
    }
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);

  return new Response(JSON.stringify({ counts, configured: true }), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=60",
    },
  });
};

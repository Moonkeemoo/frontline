/**
 * POST /api/vote — increment vote count for a post.
 * Deduplicates by SHA-256(IP + User-Agent) for 1 year.
 *
 * Bound to Cloudflare KV namespace `FRONTLINE_VOTES` via Pages → Settings →
 * Functions → KV namespace bindings (variable name: FRONTLINE_VOTES).
 */

interface Env {
  FRONTLINE_VOTES: KVNamespace;
}

interface VoteBody {
  postId?: string;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  if (!env.FRONTLINE_VOTES) {
    return json({ error: "voting backend not configured" }, 503);
  }

  let body: VoteBody;
  try {
    body = (await request.json()) as VoteBody;
  } catch {
    return json({ error: "invalid JSON" }, 400);
  }

  const postId = body.postId;
  if (
    !postId ||
    typeof postId !== "string" ||
    postId.length > 200 ||
    !/^[\w./-]+$/.test(postId)
  ) {
    return json({ error: "invalid postId" }, 400);
  }

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const ua = (request.headers.get("User-Agent") || "").slice(0, 200);
  const fp = await sha256(`${ip}:${ua}`);
  const fpKey = `fp:${fp}:${postId}`;
  const countKey = `count:${postId}`;

  const existing = await env.FRONTLINE_VOTES.get(fpKey);
  if (existing) {
    const current = parseInt(
      (await env.FRONTLINE_VOTES.get(countKey)) || "0",
      10,
    );
    return json({ ok: true, alreadyVoted: true, count: current });
  }

  const current = parseInt((await env.FRONTLINE_VOTES.get(countKey)) || "0", 10);
  const next = current + 1;
  await Promise.all([
    env.FRONTLINE_VOTES.put(countKey, String(next)),
    env.FRONTLINE_VOTES.put(fpKey, "1", { expirationTtl: 86400 * 365 }),
  ]);

  return json({ ok: true, count: next });
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(s),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

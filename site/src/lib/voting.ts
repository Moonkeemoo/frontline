/**
 * Client-side vote API with localStorage fallback for local dev / when
 * the Cloudflare backend is unavailable.
 */

const LS_KEY = "frontline:votes";

export type VoteCounts = Record<string, number>;

export async function getVoteCounts(): Promise<{
  counts: VoteCounts;
  fromBackend: boolean;
}> {
  try {
    const res = await fetch("/api/votes", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as { counts?: VoteCounts; configured?: boolean };
    if (data.configured === false) {
      return { counts: readLocal(), fromBackend: false };
    }
    return { counts: data.counts || {}, fromBackend: true };
  } catch {
    return { counts: readLocal(), fromBackend: false };
  }
}

export async function castVote(
  postId: string,
): Promise<{ ok: boolean; count?: number; alreadyVoted?: boolean; fromBackend: boolean }> {
  if (hasVoted(postId)) {
    return { ok: true, alreadyVoted: true, fromBackend: false };
  }

  try {
    const res = await fetch("/api/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ postId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as {
      ok?: boolean;
      count?: number;
      alreadyVoted?: boolean;
    };
    markVoted(postId);
    return {
      ok: !!data.ok,
      count: data.count,
      alreadyVoted: !!data.alreadyVoted,
      fromBackend: true,
    };
  } catch {
    // Local-only fallback (dev mode or backend down)
    markVoted(postId);
    const local = readLocal();
    local[postId] = (local[postId] || 0) + 1;
    saveLocal(local);
    return { ok: true, count: local[postId], fromBackend: false };
  }
}

export function hasVoted(postId: string): boolean {
  try {
    const voted = JSON.parse(localStorage.getItem(`${LS_KEY}:voted`) || "{}");
    return Boolean(voted[postId]);
  } catch {
    return false;
  }
}

function markVoted(postId: string): void {
  try {
    const voted = JSON.parse(localStorage.getItem(`${LS_KEY}:voted`) || "{}");
    voted[postId] = 1;
    localStorage.setItem(`${LS_KEY}:voted`, JSON.stringify(voted));
  } catch {
    /* ignore */
  }
}

function readLocal(): VoteCounts {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}") as VoteCounts;
  } catch {
    return {};
  }
}

function saveLocal(counts: VoteCounts): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(counts));
  } catch {
    /* ignore */
  }
}

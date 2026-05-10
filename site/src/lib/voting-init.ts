/**
 * Wires up vote buttons across the site:
 * - Loads counts on DOMContentLoaded, paints them
 * - Click handler casts vote, marks button as voted
 * - Falls back to localStorage transparently if backend is unavailable
 */

import { castVote, getVoteCounts, hasVoted } from "./voting";

async function init(): Promise<void> {
  const buttons = Array.from(
    document.querySelectorAll<HTMLElement>("[data-vote-id]"),
  );
  if (buttons.length === 0) return;

  const { counts, fromBackend } = await getVoteCounts();

  for (const btn of buttons) {
    const postId = btn.dataset.voteId!;
    const countEl = btn.querySelector<HTMLElement>(".vote-count");
    const initialCount = counts[postId] ?? 0;
    if (countEl) countEl.textContent = String(initialCount);
    btn.dataset.count = String(initialCount);

    if (!fromBackend) {
      btn.title = "Локальний голос — community-count активується після deploy";
    }

    if (hasVoted(postId)) {
      btn.classList.add("voted");
    }

    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (btn.classList.contains("voted") || btn.classList.contains("voting")) {
        return;
      }
      btn.classList.add("voting");
      try {
        const result = await castVote(postId);
        btn.classList.remove("voting");
        btn.classList.add("voted");
        const newCount =
          result.count ?? Number(btn.dataset.count || "0") + 1;
        btn.dataset.count = String(newCount);
        if (countEl) countEl.textContent = String(newCount);
      } catch {
        btn.classList.remove("voting");
      }
    });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  void init();
}

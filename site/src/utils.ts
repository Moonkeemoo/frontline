/** Display prefix for a paper's external identifier. */
export function sourceLabel(source: string): string {
  switch (source) {
    case "iacr_eprint":
      return "IACR";
    case "openreview":
      return "OpenReview";
    default:
      return "arXiv";
  }
}

/** Friendly label for the discovery signal that surfaced a paper. */
export function signalLabel(source: string): string {
  switch (source) {
    case "huggingface_daily":
      return "HF curated";
    case "hackernews":
      return "HN community";
    case "iacr_eprint":
      return "IACR new";
    case "openreview":
      return "OpenReview";
    case "arxiv_rss":
      return "arXiv recency";
    default:
      return source;
  }
}

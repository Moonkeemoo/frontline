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

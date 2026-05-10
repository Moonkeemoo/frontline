import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const posts = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/posts" }),
  schema: z.object({
    title: z.string(),
    tldr: z.string(),
    tags: z.array(z.string()),
    read_min: z.number(),
    arxiv_id: z.string(),
    arxiv_url: z.string().url(),
    authors: z.array(z.string()),
    source: z.enum(["huggingface_daily", "arxiv_rss", "openreview"]),
    publish_date: z.string(),
    submitted_at: z.string().optional(),
  }),
});

export const collections = { posts };

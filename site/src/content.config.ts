import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const baseSchema = z.object({
  title: z.string(),
  tldr: z.string(),
  tags: z.array(z.string()),
  read_min: z.number(),
  arxiv_id: z.string(),
  arxiv_url: z.string().url(),
  authors: z.array(z.string()),
  source: z.enum([
    "huggingface_daily",
    "arxiv_rss",
    "iacr_eprint",
    "openreview",
  ]),
  publish_date: z.string(),
  submitted_at: z.string().optional(),
});

const issueSchema = z.object({
  severity: z.enum(["high", "medium", "low"]),
  category: z.string(),
  description: z.string(),
  evidence: z.string(),
});

const critiqueSchema = z.object({
  verdict: z.string(),
  issues: z.array(issueSchema),
  recommendation: z.string(),
  regenerate_feedback: z.string().nullable().optional(),
});

const posts = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/posts" }),
  schema: baseSchema,
});

const queue = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/queue" }),
  schema: baseSchema.extend({ critique: critiqueSchema.optional() }),
});

export const collections = { posts, queue };

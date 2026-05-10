import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { APIRoute } from "astro";
import { parse as parseYaml } from "yaml";

const __dirname = dirname(fileURLToPath(import.meta.url));
const GLOSSARY_PATH = resolve(__dirname, "../../../pipeline/glossary.yaml");

export const prerender = true;

export const GET: APIRoute = () => {
  const yamlContent = readFileSync(GLOSSARY_PATH, "utf-8");
  const data = parseYaml(yamlContent);
  return new Response(JSON.stringify(data), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=3600",
    },
  });
};

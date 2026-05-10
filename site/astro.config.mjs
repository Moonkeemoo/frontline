import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://frontline.ua",
  markdown: {
    shikiConfig: {
      theme: "github-dark-dimmed",
      wrap: true,
    },
  },
});

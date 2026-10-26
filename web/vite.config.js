import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFile } from "node:fs/promises";

export default defineConfig({
  plugins: [react(), {
    name: "local-vocabulary-only",
    configureServer(server) {
      server.middlewares.use("/vocabulary.json", async (_req, res) => {
        try {
          const data = await readFile(new URL("../data/vocabulary.json", import.meta.url), "utf8");
          res.setHeader("Content-Type", "application/json");
          res.setHeader("Cache-Control", "no-store");
          res.end(data);
        } catch { res.statusCode = 404; res.end(); }
      });
    },
  }],
  publicDir: false,
  server: { host: "127.0.0.1", port: 47832, strictPort: true },
});

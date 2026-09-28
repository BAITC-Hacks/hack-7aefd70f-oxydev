import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Бэкенд поднимается на 8000. В деве ходим к нему через прокси,
// в сборке фронт отдаётся тем же FastAPI, поэтому пути относительные.
const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ["/analyze", "/counterfactual", "/examples", "/health"].map((path) => [
        path,
        { target: backend, changeOrigin: true },
      ]),
    ),
  },
});

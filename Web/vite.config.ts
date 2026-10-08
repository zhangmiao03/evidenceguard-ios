import { defineConfig } from "vite";
export default defineConfig({
  server: {
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8790", changeOrigin: true } },
  },
});

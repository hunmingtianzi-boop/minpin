import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../..", "VITE_");
  const apiProxyTarget =
    env.VITE_DEV_API_PROXY_TARGET?.trim() || "http://127.0.0.1:8000";

  return {
    envDir: "../..",
    plugins: [react(), tailwindcss()],
    server: {
      host: "127.0.0.1",
      port: 4173,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
    },
  };
});

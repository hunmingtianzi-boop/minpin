import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../..", "VITE_");
  const apiProxyTarget =
    env.VITE_DEV_API_PROXY_TARGET?.trim() || "http://127.0.0.1:8000";

  return {
    envDir: "../..",
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 4174,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 4174,
    },
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              {
                name: "react-runtime",
                test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
                priority: 3,
              },
              {
                name: "fluent-ui",
                test: /node_modules[\\/](@fluentui|@griffel)[\\/]/,
                priority: 2,
              },
              {
                name: "vendor",
                test: /node_modules[\\/]/,
                priority: 1,
              },
            ],
          },
        },
      },
    },
  };
});

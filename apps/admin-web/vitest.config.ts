import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    clearMocks: true,
    // Fluent UI's portal/focus management uses animation frames. Capping file
    // workers keeps those accessibility transitions inside Testing Library's
    // normal async window on high-core development machines.
    maxWorkers: 4,
  },
});

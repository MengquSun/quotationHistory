import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { nodePolyfills } from "vite-plugin-node-polyfills";

export default defineConfig({
  base: "/isislike/",
  plugins: [
    nodePolyfills({
      include: ["process", "util", "assert", "buffer", "stream"],
      globals: {
        process: true,
        global: true,
        Buffer: true,
      },
    }),
    react(),
  ],
  define: {
    "process.env.NODE_ENV": JSON.stringify(process.env.NODE_ENV ?? "development"),
  },
  server: {
    port: 5173,
  },
  optimizeDeps: {
    include: ["ketcher-core", "ketcher-react", "ketcher-standalone"],
    esbuildOptions: {
      define: {
        global: "globalThis",
      },
    },
  },
  build: {
    outDir: "../static/isislike",
    emptyOutDir: true,
    commonjsOptions: {
      include: [
        /ketcher-standalone/,
        /ketcher-react/,
        /ketcher-core/,
        /node_modules/,
      ],
      transformMixedEsModules: true,
    },
  },
  worker: {
    format: "es",
  },
});

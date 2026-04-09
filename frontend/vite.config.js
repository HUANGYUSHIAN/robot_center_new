import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function parseExternal(raw) {
  const s = String(raw ?? "").trim().toLowerCase();
  return s === "true" || s === "1" || s === "yes";
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const external = parseExternal(env.EXTERNAL);
  const wsTarget = env.TMUI_WS_PROXY_TARGET || "http://127.0.0.1:8765";
  const wsProxy = {
    "/ws": {
      target: wsTarget,
      ws: true,
      changeOrigin: true
    }
  };

  return {
    plugins: [react()],
    define: {
      // 由 .env 的 EXTERNAL 推導，避免 JSON.stringify(boolean) 在 bundle 中變成字串造成誤判
      "import.meta.env.VITE_TMUI_EXTERNAL": JSON.stringify(external ? "true" : "false")
    },
    server: {
      host: "0.0.0.0",
      port: Number(env.PORT || 5173),
      // 必須為 boolean true；字串 "all" 無效，會導致 ngrok 等 Host 被 403
      allowedHosts: true,
      ...(external ? { proxy: wsProxy } : {})
    },
    preview: {
      host: "0.0.0.0",
      port: Number(env.PORT || 5173),
      allowedHosts: true,
      ...(external ? { proxy: wsProxy } : {})
    }
  };
});

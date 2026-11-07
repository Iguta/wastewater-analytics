import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { mockApi } from "./mock/mockApi";

// The API is FastAPI on 127.0.0.1:8000 (ARCHITECTURE section 8.2).
// In production the same server serves frontend/dist, so the UI always uses relative /api URLs.
export default defineConfig({
  plugins: [react(), mockApi()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});

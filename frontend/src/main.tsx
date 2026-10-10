import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/globals.css";
import { App } from "@/app/App";

function readPreference(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    /* storage unavailable — fall back to defaults */
    return null;
  }
}

const storedTheme = readPreference("cybersaarthi-theme");
const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
if (storedTheme === "dark" || (storedTheme === "system" && systemDark)) {
  document.documentElement.classList.add("dark");
}
document.documentElement.lang = readPreference("cybersaarthi-language") === "hi" ? "hi" : "en";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
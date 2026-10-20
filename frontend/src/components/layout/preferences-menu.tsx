import { useEffect, useState } from "react";
import { Globe2, Moon, Sun, Monitor } from "lucide-react";
import { getLanguage, setLanguage, t, type Language } from "@/lib/i18n";

function readStoredTheme(): "light" | "dark" | "system" {
  try {
    const value = localStorage.getItem("cybersaarthi-theme");
    return value === "dark" || value === "system" ? value : "light";
  } catch {
    /* storage unavailable (tests/private mode) */
    return "light";
  }
}

export function PreferencesMenu() {
  const [language, setLang] = useState<Language>(getLanguage);
  const [theme, setTheme] = useState<"light" | "dark" | "system">(readStoredTheme);

  useEffect(() => {
    const apply = () => {
      const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const dark = theme === "dark" || (theme === "system" && systemDark);
      document.documentElement.classList.toggle("dark", dark);
      document.documentElement.style.colorScheme = dark ? "dark" : "light";
    };
    apply();
    try {
      localStorage.setItem("cybersaarthi-theme", theme);
    } catch {
      /* storage unavailable — keep in-memory only */
    }
  }, [theme]);

  useEffect(() => {
    const onLanguage = () => setLang(getLanguage());
    window.addEventListener("cybersaarthi-language-change", onLanguage);
    return () => window.removeEventListener("cybersaarthi-language-change", onLanguage);
  }, []);

  const changeLanguage = (value: Language) => {
    setLanguage(value);
    setLang(value);
  };

  return (
    <div className="flex items-center gap-1.5">
      <div className="hidden items-center gap-1 border border-border bg-surface-2 p-1 sm:flex" aria-label={t("theme", language)}>
        <button type="button" aria-label={t("light", language)} onClick={() => setTheme("light")} className={`grid size-7 place-items-center ${theme === "light" ? "bg-surface text-accent shadow-sm" : "text-muted hover:text-foreground"}`}>
          <Sun className="size-3.5" />
        </button>
        <button type="button" aria-label={t("dark", language)} onClick={() => setTheme("dark")} className={`grid size-7 place-items-center ${theme === "dark" ? "bg-surface text-accent shadow-sm" : "text-muted hover:text-foreground"}`}>
          <Moon className="size-3.5" />
        </button>
        <button type="button" aria-label={t("system", language)} onClick={() => setTheme("system")} className={`grid size-7 place-items-center ${theme === "system" ? "bg-surface text-accent shadow-sm" : "text-muted hover:text-foreground"}`}>
          <Monitor className="size-3.5" />
        </button>
      </div>
      <label className="inline-flex h-9 items-center gap-1.5 border border-border bg-surface-2 px-2 text-xs text-muted">
        <Globe2 className="size-3.5" />
        <span className="sr-only">{t("language", language)}</span>
        <select value={language} onChange={(e) => changeLanguage(e.target.value as Language)} className="bg-transparent font-medium outline-none">
          <option value="en">{t("english", language)}</option>
          <option value="hi">{t("hindi", language)}</option>
        </select>
      </label>
    </div>
  );
}

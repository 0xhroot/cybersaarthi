export type Language = "en" | "hi";

const KEY = "cybersaarthi-language";

export const translations = {
  en: {
    dashboard: "Dashboard",
    cases: "Cases",
    audit: "Audit log",
    users: "Users",
    settings: "Settings",
    search: "Search cases, entities, evidence...",
    signOut: "Sign out",
    theme: "Theme",
    language: "Language",
    light: "Light",
    dark: "Dark",
    system: "System",
    english: "English",
    hindi: "हिन्दी",
    secureWorkspace: "Secure workspace",
  },
  hi: {
    dashboard: "डैशबोर्ड",
    cases: "केस",
    audit: "ऑडिट लॉग",
    users: "उपयोगकर्ता",
    settings: "सेटिंग्स",
    search: "केस, इकाइयाँ, साक्ष्य खोजें...",
    signOut: "साइन आउट",
    theme: "थीम",
    language: "भाषा",
    light: "लाइट",
    dark: "डार्क",
    system: "सिस्टम",
    english: "English",
    hindi: "हिन्दी",
    secureWorkspace: "सुरक्षित कार्यक्षेत्र",
  },
} as const;

export function getLanguage(): Language {
  try {
    const value = localStorage.getItem(KEY);
    return value === "hi" ? "hi" : "en";
  } catch {
    /* storage unavailable (SSR/tests/private mode) */
    return "en";
  }
}

export function setLanguage(language: Language) {
  try {
    localStorage.setItem(KEY, language);
  } catch {
    /* storage unavailable — keep in-memory only */
  }
  document.documentElement.lang = language;
  window.dispatchEvent(new Event("cybersaarthi-language-change"));
}

export function t(key: keyof typeof translations.en, language = getLanguage()) {
  return translations[language][key];
}

/**
 * Theme choice, applied before first paint.
 *
 * The authority is the user's account preference, which the API serves. But
 * reading it needs a request, and a page that renders light and then flips to
 * dark is worse than one that guesses right. So the choice is mirrored into
 * localStorage and read by a small script in the document head, before the
 * browser paints anything.
 *
 * localStorage is a cache, never the source of truth: the Settings page
 * reconciles it with the account preference whenever that loads, so a
 * different machine picks up the account's choice on first visit.
 */
export const THEMES = ["system", "light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

export const THEME_STORAGE_KEY = "cerebro-theme";

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

/**
 * Put the choice on <html> so the CSS can act on it.
 *
 * "system" removes the attribute rather than resolving it here, which lets
 * the `prefers-color-scheme` media query stay in charge — including when the
 * operating system changes while the page is open.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function rememberTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private browsing, or storage disabled. The account preference still
    // applies on the next load; only the no-flash shortcut is lost.
  }
}

export function storedTheme(): Theme | null {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(raw) ? raw : null;
  } catch {
    return null;
  }
}

/**
 * Runs in the document head, before paint. Deliberately tiny and dependency
 * free: it is inlined as a string, so it cannot import anything.
 */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})();`;

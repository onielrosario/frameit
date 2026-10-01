/**
 * Extension settings, in chrome.storage.local.
 *
 * Read per call rather than cached in a module variable: the service worker is
 * ephemeral and a cached value would be as short-lived as the worker, giving
 * the illusion of caching without the benefit.
 */
export interface Settings {
  apiBaseUrl: string;
}

export const DEFAULT_SETTINGS: Settings = {
  apiBaseUrl: "http://localhost:8000",
};

export async function getSettings(): Promise<Settings> {
  const stored = await chrome.storage.local.get(["apiBaseUrl"]);
  return {
    apiBaseUrl:
      typeof stored.apiBaseUrl === "string" && stored.apiBaseUrl
        ? stored.apiBaseUrl
        : DEFAULT_SETTINGS.apiBaseUrl,
  };
}

export async function saveSettings(settings: Partial<Settings>): Promise<void> {
  await chrome.storage.local.set(settings);
}

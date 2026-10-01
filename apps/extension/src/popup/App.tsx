/**
 * Popup — settings / about only. NOT the result surface (ADR-0001).
 *
 * The stage-04 measurement readout that lived here is gone; those numbers are
 * recorded in apps/extension/docs/CONTEXT.md, which is where a measurement
 * belongs. Measurements still accumulate in chrome.storage as a drift signal.
 */
import { useEffect, useState } from "react";
import { DEFAULT_SETTINGS, getSettings, saveSettings, type Settings } from "../settings";

export function App() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void getSettings().then(setSettings);
  }, []);

  const update = (patch: Partial<Settings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    void saveSettings(patch).then(() => {
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
    });
  };

  return (
    <main>
      <h1>Frame</h1>
      <p className="tagline">Select text, right click, Frame It.</p>

      <label className="field">
        <span>API base URL</span>
        <input
          type="url"
          value={settings.apiBaseUrl}
          onChange={(event) => update({ apiBaseUrl: event.target.value })}
          spellCheck={false}
        />
      </label>


      <p className="muted footnote">
        {saved ? "Saved." : "Development build."}
      </p>
    </main>
  );
}

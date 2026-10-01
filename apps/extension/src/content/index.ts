/**
 * Content script: owns the shadow-root overlay (ADR-0001).
 *
 * NOT declared in manifest `content_scripts` — the background injects this file
 * with `chrome.scripting.executeScript({ files: [...] })` on user gesture. That
 * is what keeps `host_permissions` out of the manifest: `activeTab` covers the
 * tab the user just acted on, and nothing runs on any page until then.
 *
 * Injecting the same file twice re-executes it, so this guards re-entry and
 * keeps a single mount for the tab's lifetime.
 */
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { Overlay } from "./Overlay";
import overlayCss from "./overlay.css?inline";
import type { FrameMessage } from "../types";

const HOST_ID = "frame-overlay-host";
const GUARD = "__frameOverlayInstalled";

interface GuardedWindow extends Window {
  [GUARD]?: boolean;
}

function mount(): { render: (state: FrameMessage) => void } {
  const existing = document.getElementById(HOST_ID);
  existing?.remove();

  const host = document.createElement("div");
  host.id = HOST_ID;
  // `all: initial` on the host, before anything else. Host-page rules targeting
  // div, [id], or * would otherwise inherit straight through the boundary.
  host.style.all = "initial";

  const shadow = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = overlayCss;
  shadow.appendChild(style);

  const container = document.createElement("div");
  shadow.appendChild(container);

  // documentElement, not body: some pages replace or restyle body wholesale.
  document.documentElement.appendChild(host);

  let root: Root | null = null;

  const close = (): void => {
    root?.unmount();
    root = null;
    host.remove();
    document.removeEventListener("keydown", onKeydown, true);
  };

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") close();
  }

  const render = (state: FrameMessage): void => {
    if (!host.isConnected) document.documentElement.appendChild(host);
    root ??= createRoot(container);
    root.render(createElement(Overlay, { state, onClose: close }));
    document.addEventListener("keydown", onKeydown, true);
  };

  return { render };
}

const guardedWindow = window as GuardedWindow;

if (!guardedWindow[GUARD]) {
  guardedWindow[GUARD] = true;

  const overlay = mount();

  chrome.runtime.onMessage.addListener((message: FrameMessage, _sender, sendResponse) => {
    // Every variant renders. A message this build does not know is ignored
    // rather than crashed on.
    if (
      message.type !== "FRAME_LOADING" &&
      message.type !== "FRAME_RESULT" &&
      message.type !== "FRAME_ERROR"
    ) {
      return undefined;
    }
    overlay.render(message);
    sendResponse({ ok: true });
    return undefined;
  });
}

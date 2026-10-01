import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./popup.css";

const container = document.getElementById("root");
if (!container) throw new Error("popup root missing");
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

import { FluentProvider } from "@fluentui/react-components";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import { adminLightTheme } from "./theme";

const root = document.getElementById("root");
if (!root) throw new Error("Application root element is missing");

createRoot(root).render(
  <StrictMode>
    <FluentProvider theme={adminLightTheme} className="fluent-root">
      <App />
    </FluentProvider>
  </StrictMode>,
);

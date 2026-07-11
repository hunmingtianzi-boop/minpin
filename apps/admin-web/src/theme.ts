import type { Theme } from "@fluentui/react-components";
import { webLightTheme } from "@fluentui/react-components";

const cobalt = "#0f4cbd";

export const adminLightTheme: Theme = {
  ...webLightTheme,
  colorBrandBackground: cobalt,
  colorBrandBackgroundHover: "#0c3f9e",
  colorBrandBackgroundPressed: "#09347f",
  colorBrandBackgroundSelected: "#0c3f9e",
  colorBrandForeground1: cobalt,
  colorBrandForeground2: "#0c3f9e",
  colorBrandForegroundLink: cobalt,
  colorBrandForegroundLinkHover: "#0c3f9e",
  colorBrandForegroundLinkPressed: "#09347f",
  colorCompoundBrandForeground1: cobalt,
  colorCompoundBrandForeground1Hover: "#0c3f9e",
  colorCompoundBrandForeground1Pressed: "#09347f",
  colorCompoundBrandBackground: cobalt,
  colorCompoundBrandBackgroundHover: "#0c3f9e",
  colorCompoundBrandBackgroundPressed: "#09347f",
  colorCompoundBrandStroke: cobalt,
  colorCompoundBrandStrokeHover: "#0c3f9e",
  colorCompoundBrandStrokePressed: "#09347f",
  borderRadiusSmall: "8px",
  borderRadiusMedium: "8px",
  borderRadiusLarge: "8px",
  borderRadiusXLarge: "8px",
};

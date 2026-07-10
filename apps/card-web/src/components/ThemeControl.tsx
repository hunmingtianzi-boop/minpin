import { Desktop, Moon, Sun } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

export type ThemeMode = "system" | "dark" | "light";

const themeOrder: ThemeMode[] = ["system", "dark", "light"];

const themeLabels: Record<ThemeMode, string> = {
  system: "跟随系统",
  dark: "深色模式",
  light: "浅色模式",
};

function getInitialTheme(storageKey: string, defaultMode: ThemeMode): ThemeMode {
  const saved = window.localStorage.getItem(storageKey);
  return saved === "dark" || saved === "light" || saved === "system"
    ? saved
    : defaultMode;
}

export function ThemeControl({
  storageKey = "cf-card-theme",
  defaultMode = "system",
  lightThemeColor,
  darkThemeColor,
}: {
  storageKey?: string;
  defaultMode?: ThemeMode;
  lightThemeColor: string;
  darkThemeColor: string;
}) {
  const [theme, setTheme] = useState<ThemeMode>(() =>
    getInitialTheme(storageKey, defaultMode),
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const applyTheme = () => {
      const resolved = theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved;
      window.localStorage.setItem(storageKey, theme);
      const themeMeta = document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
      if (themeMeta) themeMeta.content = resolved === "dark" ? darkThemeColor : lightThemeColor;
    };

    applyTheme();
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [darkThemeColor, lightThemeColor, storageKey, theme]);

  const Icon = useMemo(() => {
    if (theme === "dark") return Moon;
    if (theme === "light") return Sun;
    return Desktop;
  }, [theme]);

  const cycleTheme = () => {
    const nextIndex = (themeOrder.indexOf(theme) + 1) % themeOrder.length;
    setTheme(themeOrder[nextIndex]);
  };

  return (
    <button
      className="theme-control"
      type="button"
      onClick={cycleTheme}
      aria-label={`${themeLabels[theme]}，点击切换显示模式`}
      title={`${themeLabels[theme]}，点击切换`}
    >
      <Icon aria-hidden="true" size={18} weight="regular" />
      <span>{themeLabels[theme]}</span>
    </button>
  );
}

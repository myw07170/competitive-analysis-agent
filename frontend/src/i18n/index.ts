import { en } from "./en";
import { zh } from "./zh";

export type Locale = "zh-CN" | "en-US";

const BUNDLES: Record<Locale, Record<string, string>> = {
  "zh-CN": zh,
  "en-US": en,
};

export function marketToLocale(market: string): Locale {
  if (market === "cn") return "zh-CN";
  if (market === "us") return "en-US";
  // 扩展点：未来的市场在此注册其默认 locale。
  return "en-US";
}

export function makeT(locale: Locale) {
  const bundle = BUNDLES[locale] || BUNDLES["en-US"];
  return (key: string, vars?: Record<string, string | number>) => {
    let s = bundle[key] ?? key;
    if (vars) for (const k of Object.keys(vars)) s = s.replace(`{${k}}`, String(vars[k]));
    return s;
  };
}

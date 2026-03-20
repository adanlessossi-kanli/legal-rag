export const locales = ["en", "fr", "de", "it"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

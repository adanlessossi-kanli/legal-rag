import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";
import { locales, defaultLocale, type Locale } from "./config";

export default getRequestConfig(async ({ requestLocale }) => {
  const locale = (await requestLocale) ?? defaultLocale;
  if (!locales.includes(locale as Locale)) notFound();
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});

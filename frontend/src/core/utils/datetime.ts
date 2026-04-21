import { formatDistanceToNow } from "date-fns";
import { enUS as dateFnsEnUS, zhCN as dateFnsZhCN } from "date-fns/locale";

import { detectLocale, type Locale } from "@/core/i18n";
import { getLocaleFromCookie } from "@/core/i18n/cookies";

function getDateFnsLocale(locale: Locale) {
  switch (locale) {
    case "zh-CN":
      return dateFnsZhCN;
    case "en-US":
    default:
      return dateFnsEnUS;
  }
}

function normalizeTimestampNumber(value: number): Date | null {
  if (!Number.isFinite(value)) {
    return null;
  }
  // DeerFlow thread APIs may return Unix timestamps in seconds as strings.
  const milliseconds = Math.abs(value) < 1e12 ? value * 1000 : value;
  const normalized = new Date(milliseconds);
  return Number.isNaN(normalized.getTime()) ? null : normalized;
}

export function normalizeDateInput(
  value: Date | string | number | null | undefined,
): Date | null {
  if (value == null) {
    return null;
  }

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (typeof value === "number") {
    return normalizeTimestampNumber(value);
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const asNumber = Number(trimmed);
  if (!Number.isNaN(asNumber)) {
    return normalizeTimestampNumber(asNumber);
  }

  const normalized = new Date(trimmed);
  return Number.isNaN(normalized.getTime()) ? null : normalized;
}

export function formatTimeAgo(
  date: Date | string | number,
  locale?: Locale,
): string {
  const normalized = normalizeDateInput(date);
  if (!normalized) {
    return "";
  }

  const effectiveLocale =
    locale ??
    (getLocaleFromCookie() as Locale | null) ??
    // Fallback when cookie is missing (or on first render)
    detectLocale();
  return formatDistanceToNow(normalized, {
    addSuffix: true,
    locale: getDateFnsLocale(effectiveLocale),
  });
}

/** Dates are stored as a shifted Date whose UTC fields are the site's local date. */
export function listDate(date: Date): string {
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${month}/${day}`;
}

export function fullDate(date: Date): string {
  return `${date.getUTCFullYear()} 年 ${date.getUTCMonth() + 1} 月 ${date.getUTCDate()} 日`;
}

export function isoDate(date: Date): string {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, '0');
  const d = String(date.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function yearOf(date: Date): string {
  return String(date.getUTCFullYear());
}

export function localDate(iso: string, offsetHours: number): Date {
  return new Date(Date.parse(iso) + offsetHours * 3600 * 1000);
}

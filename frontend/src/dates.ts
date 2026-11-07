// Days are UTC dates (ARCHITECTURE 3.3). The UI steps by whole days; as_of_utc is that day at 00:00Z.
const DAY_MS = 86_400_000;

export const dayOf = (iso: string) => iso.slice(0, 10);
export const toAsOf = (day: string) => `${day}T00:00:00Z`;
export const addDays = (day: string, n: number) =>
  new Date(Date.parse(`${day}T00:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);
export const daysBetween = (a: string, b: string) =>
  Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY_MS);
export const isDay = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`));

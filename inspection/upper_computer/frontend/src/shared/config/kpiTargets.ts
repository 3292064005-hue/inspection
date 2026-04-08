function normalizePercent(value: string | undefined, fallback: string): string {
  const text = String(value ?? '').trim();
  return text || fallback;
}

function normalizeDuration(value: string | undefined, fallback: string): string {
  const text = String(value ?? '').trim();
  return text || fallback;
}

export const kpiTargets = {
  detectionAccuracy: normalizePercent(import.meta.env.VITE_KPI_TARGET_DETECTION_ACCURACY, '≥ 95%'),
  sortingAccuracy: normalizePercent(import.meta.env.VITE_KPI_TARGET_SORTING_ACCURACY, '≥ 98%'),
  cycleTime: normalizeDuration(import.meta.env.VITE_KPI_TARGET_CYCLE_TIME, '≤ 2.5 s'),
};

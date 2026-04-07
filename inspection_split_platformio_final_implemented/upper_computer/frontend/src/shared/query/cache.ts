type CacheEntry<T> = {
  value: T;
  expiresAt: number;
  updatedAt: number;
};

const cache = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

export interface CacheOptions {
  ttlMs?: number;
  force?: boolean;
  allowStale?: boolean;
}

export async function fetchWithCache<T>(key: string, loader: () => Promise<T>, options: CacheOptions = {}): Promise<T> {
  const ttlMs = options.ttlMs ?? 5000;
  const now = Date.now();
  const hit = cache.get(key) as CacheEntry<T> | undefined;

  if (!options.force && hit && hit.expiresAt > now) {
    return hit.value;
  }

  const pending = inflight.get(key) as Promise<T> | undefined;
  if (!options.force && pending) return pending;

  if (!options.force && options.allowStale && hit) {
    void refreshCache(key, loader, ttlMs);
    return hit.value;
  }

  return refreshCache(key, loader, ttlMs);
}

async function refreshCache<T>(key: string, loader: () => Promise<T>, ttlMs: number): Promise<T> {
  const job = loader().then((value) => {
    const now = Date.now();
    cache.set(key, {
      value,
      updatedAt: now,
      expiresAt: now + ttlMs,
    });
    inflight.delete(key);
    return value;
  }).catch((error) => {
    inflight.delete(key);
    throw error;
  });

  inflight.set(key, job as Promise<unknown>);
  return job;
}

export function peekCache<T>(key: string): T | null {
  return (cache.get(key)?.value as T | undefined) ?? null;
}

export function invalidateCache(prefix = ''): void {
  if (!prefix) {
    cache.clear();
    inflight.clear();
    return;
  }

  Array.from(cache.keys()).forEach((key) => {
    if (key.startsWith(prefix)) cache.delete(key);
  });
  Array.from(inflight.keys()).forEach((key) => {
    if (key.startsWith(prefix)) inflight.delete(key);
  });
}

export function cacheKeys(prefix = ''): string[] {
  return Array.from(cache.keys()).filter((key) => (prefix ? key.startsWith(prefix) : true));
}

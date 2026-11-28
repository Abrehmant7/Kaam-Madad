import { useCallback, useState } from "react";

/**
 * Unsent input kept in memory while the user moves between screens of the app (chat ↔ quote, new request ↔
 * dashboard). Nothing is written to the browser's storage: a reload or logout clears it, so typed text and
 * recordings never outlive the session on a shared phone.
 */
const store = new Map<string, unknown>();

export function readDraft<T>(key: string): T | undefined {
  return store.get(key) as T | undefined;
}

export function writeDraft(key: string, value: unknown): void {
  if (value === undefined || value === null || value === "") store.delete(key);
  else store.set(key, value);
}

export function clearDraft(key: string): void {
  store.delete(key);
}

/** Forget every draft (logout). */
export function clearDrafts(): void {
  store.clear();
}

/** useState that also remembers its value under `key` until the component sets it back to empty. */
export function useDraftState<T>(key: string, initial: T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => readDraft<T>(key) ?? initial);
  const set = useCallback((next: T) => {
    setValue(next);
    writeDraft(key, next);
  }, [key]);
  return [value, set];
}

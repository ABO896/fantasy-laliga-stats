import "@testing-library/jest-dom/vitest";

// This toolchain's jsdom + Node combination leaves `localStorage`
// unusable under test (neither a jsdom Storage instance nor a thrown
// SecurityError — just `undefined`). Polyfill a minimal in-memory
// Storage so components that persist to localStorage (e.g.
// RefreshControls) can be tested against real reads/writes instead of
// only ever hitting their try/catch fallback.
function hasUsableLocalStorage(): boolean {
  try {
    return typeof globalThis.localStorage === "object" && globalThis.localStorage !== null;
  } catch {
    return false;
  }
}

if (!hasUsableLocalStorage()) {
  const store = new Map<string, string>();
  const memoryStorage: Storage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: memoryStorage,
    writable: true,
    configurable: true,
  });
}

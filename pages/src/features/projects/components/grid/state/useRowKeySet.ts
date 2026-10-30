import {useMemo, useState} from 'react';

const updateKeys = (change: (next: Set<string>) => void) => (current: Set<string>) => {
  const next = new Set(current);
  change(next);
  return next;
};

/** A set of row keys (expanded rows, checked rows) with stable updaters for the changes the grid makes. */
export function useRowKeySet() {
  const [keys, setKeys] = useState<Set<string>>(new Set());
  const actions = useMemo(
    () => ({
      replace: (rowKeys: Iterable<string>) => setKeys(new Set(rowKeys)),
      toggle: (rowKey: string) =>
        setKeys(
          updateKeys((next) => {
            if (next.has(rowKey)) {
              next.delete(rowKey);
            } else {
              next.add(rowKey);
            }
          }),
        ),
      add: (rowKeys: Iterable<string>) =>
        setKeys(
          updateKeys((next) => {
            for (const rowKey of rowKeys) next.add(rowKey);
          }),
        ),
      remove: (rowKeys: Iterable<string>) =>
        setKeys(
          updateKeys((next) => {
            for (const rowKey of rowKeys) next.delete(rowKey);
          }),
        ),
      /** Drop keys of rows that no longer exist, keeping the rest. */
      retainOnly: (rowKeys: ReadonlySet<string>) =>
        setKeys((current) => new Set([...current].filter((rowKey) => rowKeys.has(rowKey)))),
    }),
    [],
  );
  return [keys, actions] as const;
}

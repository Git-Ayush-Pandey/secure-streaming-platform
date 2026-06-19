import { useEffect, useRef } from 'react';

/**
 * Calls `fn` immediately and then every `intervalMs` milliseconds.
 * Stops polling when component unmounts.
 */
export function usePolling(fn, intervalMs = 5000, deps = []) {
  const fnRef = useRef(fn);
  useEffect(() => { fnRef.current = fn; }, [fn]);

  useEffect(() => {
    let active = true;
    fnRef.current();
    const id = setInterval(() => { if (active) fnRef.current(); }, intervalMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, deps); // eslint-disable-line
}

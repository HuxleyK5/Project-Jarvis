import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchHealth, type Health } from '../services/api';

export type Connection = 'checking' | 'online' | 'offline';

export function useBackend() {
  const [connection, setConnection] = useState<Connection>('checking');
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [attempt, setAttempt] = useState(0);
  const busy = useRef(false);
  const retry = useCallback(() => { if (!busy.current) setAttempt(value => value + 1); }, []);

  useEffect(() => {
    let disposed = false;
    let active: AbortController | null = null;
    async function check() {
      if (active) return;
      const controller = new AbortController();
      active = controller;
      busy.current = true;
      setChecking(true);
      const timeout = window.setTimeout(() => controller.abort(), 4000);
      try {
        const result = await fetchHealth(controller.signal);
        if (!disposed) {
          setHealth(result);
          setConnection('online');
          setError(null);
        }
      } catch (reason) {
        if (!disposed) {
          setHealth(null);
          setConnection('offline');
          setError(controller.signal.aborted ? 'Connection timed out. Check that the backend is running.'
            : reason instanceof Error ? reason.message : 'Unable to reach the local backend.');
        }
      } finally {
        window.clearTimeout(timeout);
        active = null;
        if (!disposed) {
          busy.current = false;
          setChecking(false);
          setLastChecked(new Date());
        }
      }
    }
    void check();
    const timer = window.setInterval(() => void check(), 10000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      active?.abort();
      busy.current = false;
    };
  }, [attempt]);

  return { connection, health, error, checking, lastChecked, retry };
}

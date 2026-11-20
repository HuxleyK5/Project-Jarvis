import { useEffect, useRef, useState } from 'react';
import { memoryRequest, type MemorySettings, type SavedMemory, type SavedTurn } from '../services/memory';

export function useMemory() {
  const [settings, setSettings] = useState<MemorySettings>({ enabled: false, save_history: false, allowed: true });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entries, setEntries] = useState<SavedMemory[]>([]);
  const [turns, setTurns] = useState<SavedTurn[]>([]);
  const revision = useRef(0);
  useEffect(() => {
    let disposed = false;
    const version = revision.current;
    void memoryRequest<MemorySettings>('settings').then(value => { if (!disposed && version === revision.current) { setSettings(value); setReady(true); } })
      .catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : 'Memory settings could not be loaded.'); });
    return () => { disposed = true; };
  }, []);

  async function action(task: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await task(); return true; }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Memory action failed.'); return false; }
    finally { setBusy(false); }
  }
  async function load(query = '') {
    const version = ++revision.current;
    return action(async () => {
      const [items, history, config] = await Promise.all([
        memoryRequest<SavedMemory[]>(`entries?q=${encodeURIComponent(query)}`),
        memoryRequest<SavedTurn[]>(`conversations?q=${encodeURIComponent(query)}`),
        memoryRequest<MemorySettings>('settings'),
      ]);
      if (version === revision.current) { setEntries(items); setTurns(history); setSettings(config); setReady(true); }
    });
  }
  async function configure(enabled: boolean, save_history: boolean, recall_history = settings.recall_history ?? false) {
    ++revision.current;
    const previous = settings;
    setSettings({ ...settings, enabled, save_history: enabled && save_history, recall_history: enabled && recall_history });
    const success = await action(async () => { setSettings(await memoryRequest<MemorySettings>('settings', 'PUT', { enabled, save_history: enabled && save_history, recall_history: enabled && recall_history, approved: true })); });
    if (!success) setSettings(previous);
    return success;
  }
  async function save(kind: SavedMemory['kind'], content: string, approved: boolean, id?: number) {
    return action(async () => {
      const item = await memoryRequest<SavedMemory>(id === undefined ? 'entries' : `entries/${id}`, id === undefined ? 'POST' : 'PUT', { kind, content, approved });
      setEntries(value => [item, ...value.filter(entry => entry.id !== item.id)]);
    });
  }
  async function remove(category: 'entries' | 'conversations', id: number | string) {
    if (!window.confirm('Permanently delete this saved item from local memory? This cannot be undone in JARVIS.')) return false;
    return action(async () => {
      await memoryRequest(`${category}/${id}?confirm=true`, 'DELETE');
      if (category === 'entries') setEntries(value => value.filter(item => item.id !== id));
      else setTurns(value => value.filter(item => item.id !== id));
    });
  }
  return { settings, ready, busy, error, entries, turns, load, configure, save, remove };
}

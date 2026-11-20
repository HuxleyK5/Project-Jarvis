export interface MemorySettings { enabled: boolean; save_history: boolean; allowed: boolean; recall_history?: boolean }
export interface SavedMemory { id: number; kind: 'preference' | 'project' | 'fact'; content: string; created_at: string; updated_at: string }
export interface SavedTurn { id: string; conversation_id: string; user_text: string; assistant_text: string; created_at: string }

export async function memoryRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/memory/${path}`, { method, cache: 'no-store',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(10000) });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || 'Memory is unavailable. Restart the backend and try again.');
  return data as T;
}

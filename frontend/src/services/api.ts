export interface Health {
  status: 'ok';
  service: 'JARVIS';
  ai_connected: boolean;
}

export async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/api/health', { signal, cache: 'no-store' });
  if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}.`);
  const data: unknown = await response.json();
  if (!data || typeof data !== 'object' || !('status' in data) || data.status !== 'ok'
    || !('service' in data) || data.service !== 'JARVIS'
    || !('ai_connected' in data) || typeof data.ai_connected !== 'boolean') {
    throw new Error('Unexpected health response from backend.');
  }
  return data as Health;
}

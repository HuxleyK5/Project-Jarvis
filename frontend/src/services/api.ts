export interface Health {
  status: 'ok';
  service: 'JARVIS';
  ai_connected: boolean;
  provider?: string;
  model?: string;
  ai_status?: string;
  ai_message?: string;
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
  for (const key of ['provider', 'model', 'ai_status', 'ai_message'] as const) {
    if (key in data && typeof (data as Record<string, unknown>)[key] !== 'string') {
      throw new Error('Unexpected health response from backend.');
    }
  }
  return data as Health;
}

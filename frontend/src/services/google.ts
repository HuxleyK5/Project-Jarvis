export type GoogleService = 'calendar' | 'gmail' | 'classroom';
export interface GoogleStatus { service: GoogleService; enabled: boolean; write: boolean; send: boolean; role: 'student' | 'teacher'; status: string; client_configured: boolean; saved_authorization: boolean; requested_scopes: string[]; connection_verified: boolean }
export interface GoogleProposal { id: string; service: GoogleService; action: string; payload: object; sender?: string | null; status: string; result: unknown; error: string | null }
export type GoogleRequest = <T>(path: string, method?: string, body?: unknown) => Promise<T>;

export async function googleRequest<T>(token: string, path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/integrations/google${path}`, { method, signal, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-Jarvis-Tool-Token': token },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || `Google integration request failed (HTTP ${response.status}).`);
  return data as T;
}

export interface WorkflowPolicy { enabled: boolean; automatic_tools: string[]; eligible_automatic_tools: string[]; scheduler_available: boolean }
export interface WorkflowStep { number: number; tool: string; arguments: Record<string, unknown>; category: string; status: string; result: unknown; verification: { passed: boolean; detail: string } | null; error: string | null }
export interface Workflow { id: string; outcome: string; status: string; requires_confirmation: boolean; steps: WorkflowStep[]; error: string | null; scheduled_for: string | null; report: { completed: number[]; incomplete: number[] } }
export interface WorkflowHistory { workflow_id: string; time: string; status: string; completed: number; total: number; tools: string[] }

export async function automationRequest<T>(token: string, path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/automation${path}`, { method, signal, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-Jarvis-Tool-Token': token },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || `Workflow request failed (HTTP ${response.status}).`);
  return data as T;
}

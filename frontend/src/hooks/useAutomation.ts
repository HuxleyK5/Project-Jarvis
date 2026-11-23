import { useCallback, useEffect, useRef, useState } from 'react';
import { automationRequest, type Workflow, type WorkflowHistory, type WorkflowPolicy } from '../services/automation';

const defaults: WorkflowPolicy = { enabled: false, automatic_tools: [], eligible_automatic_tools: ['system_info', 'list_directory', 'search_files'], scheduler_available: false };
export function useAutomation(onActivity: (text: string, warning: boolean) => void) {
  const token = useRef('');
  const seen = useRef(new Set<string>());
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const [policy, setPolicy] = useState(defaults);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [history, setHistory] = useState<WorkflowHistory[]>([]);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [currentPolicy, currentFlows, currentHistory] = await Promise.all([
      automationRequest<WorkflowPolicy>(token.current, '/policy', 'GET', undefined, signal),
      automationRequest<Workflow[]>(token.current, '/workflows', 'GET', undefined, signal),
      automationRequest<WorkflowHistory[]>(token.current, '/history', 'GET', undefined, signal),
    ]);
    if (!mounted.current || signal?.aborted) return;
    setPolicy(currentPolicy); setWorkflows(currentFlows); setHistory(currentHistory);
    for (const flow of currentFlows) {
      const signature = `${flow.id}:${flow.status}:${flow.report.completed.length}`;
      if (seen.current.has(signature)) continue;
      seen.current.add(signature);
      onActivity(`Workflow ${flow.id.slice(0, 8)}: ${flow.status} (${flow.report.completed.length}/${flow.steps.length} completed)`, ['failed', 'blocked', 'cancelled', 'expired'].includes(flow.status));
    }
  }, [onActivity]);

  useEffect(() => {
    mounted.current = true;
    const current = new AbortController();
    void (async () => {
      try {
        const response = await fetch('/api/tools/session', { cache: 'no-store', signal: current.signal });
        const data = await response.json();
        if (!response.ok || typeof data.token !== 'string') throw new Error('Workflow session unavailable. Refresh after starting the backend.');
        token.current = data.token;
        await refresh(current.signal);
        if (mounted.current) setReady(true);
      } catch (error) { if (!current.signal.aborted) setNotice(error instanceof Error ? error.message : 'Workflows unavailable.'); }
    })();
    return () => { mounted.current = false; current.abort(); controller.current?.abort(); };
  }, [refresh]);

  useEffect(() => {
    if (!ready) return;
    const current = new AbortController();
    const timer = window.setInterval(() => {
      void refresh(current.signal).catch(error => { if (!current.signal.aborted && mounted.current) setNotice(error.message); });
    }, 1200);
    return () => { current.abort(); window.clearInterval(timer); };
  }, [ready, refresh]);

  async function request<T>(path: string, method = 'POST', body?: unknown) {
    if (controller.current) return;
    const current = new AbortController(); controller.current = current; setBusy(true); setNotice('');
    try {
      const data = await automationRequest<T>(token.current, path, method, body, current.signal);
      await refresh(current.signal);
      return data;
    } catch (error) { if (!current.signal.aborted && mounted.current) setNotice(error instanceof Error ? error.message : 'Workflow request failed.'); }
    finally { if (controller.current === current) { controller.current = null; if (mounted.current) setBusy(false); } }
  }
  // Cancellation stays available even while a different request is pending.
  async function cancel(id: string) {
    try { await automationRequest(token.current, `/workflows/${id}/cancel`, 'POST'); await refresh(); }
    catch (error) { if (mounted.current) setNotice(error instanceof Error ? error.message : 'Cancellation failed.'); }
  }
  function stopPlanning() { controller.current?.abort(); controller.current = null; setBusy(false); setNotice('Request cancelled. No new execution was approved. Refresh history to inspect any completed plan.'); }
  return { policy, workflows, history, notice, setNotice, busy, ready, request, cancel, stopPlanning };
}

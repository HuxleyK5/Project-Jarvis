import { useEffect, useRef, useState } from 'react';

interface Policy { enabled: boolean; roots: Record<string, string>; applications: string[]; websites: Record<string, string> }
interface Definition { name: string; description: string; input_schema: object }
interface Operation { id: string; tool: string; arguments: object; status: string; result: unknown; error: string | null }
interface Activity { id: string; tool: string; status: string; time: string }
const empty: Policy = { enabled: false, roots: {}, applications: [], websites: {} };

export default function ToolPanel({ onActivity }: { onActivity: (text: string, warning: boolean) => void }) {
  const token = useRef('');
  const seen = useRef(new Set<string>());
  const mounted = useRef(true);
  const planner = useRef<AbortController | null>(null);
  const [policy, setPolicy] = useState<Policy>(empty);
  const [catalog, setCatalog] = useState<Definition[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [directories, setDirectories] = useState('');
  const [websites, setWebsites] = useState('');
  const [applications, setApplications] = useState<string[]>([]);
  const [permissionApproval, setPermissionApproval] = useState(false);
  const [actionApproval, setActionApproval] = useState(false);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [question, setQuestion] = useState('');
  const [tool, setTool] = useState('system_info');
  const [root, setRoot] = useState('');
  const [path, setPath] = useState('.');
  const [query, setQuery] = useState('');
  const [application, setApplication] = useState('notepad');
  const [website, setWebsite] = useState('');
  const [operation, setOperation] = useState<Operation | null>(null);

  async function api<T>(url: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    const response = await fetch(`/api/tools${url}`, { method, cache: 'no-store', signal,
      headers: { 'Content-Type': 'application/json', 'X-Jarvis-Tool-Token': token.current },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.error?.message || `Tools unavailable (HTTP ${response.status}).`);
    return data as T;
  }

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void (async () => {
      try {
        const session = await api<{ token: string; catalog: Definition[] }>('/session', 'GET', undefined, controller.signal);
        if (!session.token || !Array.isArray(session.catalog)) throw new Error('Invalid tool session.');
        token.current = session.token;
        const current = await api<Policy>('/policy', 'GET', undefined, controller.signal);
        if (!mounted.current) return;
        setCatalog(session.catalog); setPolicy(current); setEnabled(current.enabled);
        setDirectories(Object.values(current.roots).join('\n')); setWebsites(Object.values(current.websites).join('\n'));
        setApplications(current.applications);
        setRoot(Object.keys(current.roots)[0] || ''); setWebsite(Object.keys(current.websites)[0] || '');
        setApplication(current.applications[0] || '');
      } catch (error) { if (!controller.signal.aborted && mounted.current) setNotice(error instanceof Error ? error.message : 'Tools unavailable.'); }
    })();
    return () => { mounted.current = false; controller.abort(); planner.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!policy.enabled) return;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const events = await api<Activity[]>('/activity', 'GET', undefined, controller.signal);
        if (!mounted.current) return;
        for (const event of [...events].reverse()) {
          if (seen.current.has(event.id)) continue;
          seen.current.add(event.id);
          onActivity(`Tool ${event.tool}: ${event.status}`, ['failed', 'rejected', 'cancelled'].includes(event.status));
        }
      } catch { /* Individual requests report actionable errors in the panel. */ }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [policy.enabled, onActivity]);

  useEffect(() => {
    if (!operation || !['running', 'pending'].includes(operation.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      void api<Operation>(`/operations/${operation.id}`, 'GET', undefined, controller.signal)
        .then(value => { if (mounted.current) setOperation(value); })
        .catch(error => { if (!controller.signal.aborted && mounted.current) setNotice(error.message); });
    }, 400);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [operation?.id, operation?.status]);

  async function act(action: () => Promise<void>) {
    setBusy(true); setNotice('');
    try { await action(); } catch (error) { if (mounted.current) setNotice(error instanceof Error ? error.message : 'Action failed.'); }
    finally { if (mounted.current) setBusy(false); }
  }
  const active = !!operation && ['pending', 'running'].includes(operation.status);
  function argumentsForTool() {
    if (tool === 'system_info') return {};
    if (tool === 'open_application') return { application };
    if (tool === 'open_website') return { website };
    return { root, path, ...(tool === 'search_files' ? { query } : {}) };
  }
  function acceptProposal(value: Operation) { setOperation(value); setActionApproval(false); }

  return <details className="voice-controls tool-controls"><summary>COMPUTER TOOLS · {policy.enabled ? 'SESSION ENABLED' : 'DISABLED'}</summary>
    <p>Every action requires an exact preview and approval. Permissions last until backend restart. Tools never edit your documents or run shell commands. Only execution metadata is saved to data/tool-audit.jsonl; results stay in server/browser memory.</p>
    <fieldset disabled={busy || planning}>
      <legend>Session permissions</legend>
      <label><input type="checkbox" checked={enabled} onChange={event => { setEnabled(event.target.checked); setPermissionApproval(false); }} /> Enable computer tools</label>
      <label>Approved folders (one absolute local path per line)<textarea aria-label="Approved folders" value={directories} onChange={event => { setDirectories(event.target.value); setPermissionApproval(false); }} placeholder="C:\Users\your-name\Documents\SelectedProject" /></label>
      <p>Choose only folders you intend JARVIS to access. Hidden/system folders and linked paths are blocked. Document reading requires another action approval and refuses detected sensitive data.</p>
      <div className="voice-actions">{['notepad', 'calculator'].map(app => <label key={app}><input type="checkbox" checked={applications.includes(app)} onChange={event => { setApplications(value => event.target.checked ? [...value, app] : value.filter(item => item !== app)); setPermissionApproval(false); }} />Allow {app}</label>)}</div>
      <label>Approved websites (one exact HTTPS URL per line)<textarea aria-label="Approved websites" value={websites} onChange={event => { setWebsites(event.target.value); setPermissionApproval(false); }} placeholder="https://example.org/" /></label>
      <label><input type="checkbox" checked={permissionApproval} onChange={event => setPermissionApproval(event.target.checked)} /> I approve these session permissions and metadata logging</label>
      <div className="voice-actions"><button type="button" disabled={!permissionApproval || !token.current} onClick={() => void act(async () => {
        const lines = (value: string) => value.split('\n').map(line => line.trim()).filter(Boolean);
        const value = await api<Policy>('/policy', 'PUT', { approved: true, enabled, directories: lines(directories), applications, websites: lines(websites) });
        setPolicy(value); setRoot(Object.keys(value.roots)[0] || ''); setWebsite(Object.keys(value.websites)[0] || '');
        setApplication(value.applications[0] || '');
        setOperation(null); setPermissionApproval(false); onActivity('Tool permissions updated; previous operations cancelled', false);
      })}>Apply approved permissions</button>
      <button type="button" disabled={!policy.enabled} onClick={() => void act(async () => {
        const value = await api<Policy>('/policy', 'PUT', { approved: true, enabled: false, directories: [], applications: [], websites: [] });
        setPolicy(value); setEnabled(false); setDirectories(''); setWebsites(''); setApplications([]); setOperation(null);
        onActivity('Computer tools disabled; outstanding operations cancelled', true);
      })}>Disable tools and revoke access</button></div>
    </fieldset>
    <fieldset disabled={!policy.enabled || busy || planning || active}>
      <legend>Ask JARVIS to propose an action</legend>
      <p>This sends your request and the approved folder/website catalog to local Ollama. It proposes one action and never runs it automatically. Ordinary chat cannot execute tools.</p>
      <label>Tool request<input aria-label="Tool request" value={question} onChange={event => setQuestion(event.target.value)} maxLength={4000} placeholder="List files in my approved project folder" /></label>
      <button type="button" disabled={!question.trim()} onClick={() => {
        const controller = new AbortController(); planner.current = controller; setPlanning(true); setNotice('');
        void api<{ proposal: Operation | null; message?: string }>('/plan', 'POST', { question }, controller.signal)
          .then(value => { if (!controller.signal.aborted) { if (value.proposal) acceptProposal(value.proposal); else setNotice(value.message || 'No tool selected.'); } })
          .catch(error => { if (!controller.signal.aborted) setNotice(error.message); })
          .finally(() => { if (planner.current === controller) { if (mounted.current) setPlanning(false); planner.current = null; } });
      }}>Ask JARVIS to select a tool</button>
    </fieldset>
    {planning && <div className="voice-actions"><span role="status">Selecting a tool; no action is running.</span><button type="button" onClick={() => { planner.current?.abort(); setPlanning(false); setNotice('Tool selection cancelled. No action was approved.'); }}>Cancel tool selection</button></div>}
    <fieldset disabled={!policy.enabled || busy || planning || active}>
      <legend>Manual tool selection</legend>
      <label>Tool<select aria-label="Computer tool" value={tool} onChange={event => setTool(event.target.value)}>{catalog.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      <p>{catalog.find(item => item.name === tool)?.description}</p>
      {['list_directory', 'search_files', 'read_text'].includes(tool) && <>
        <label>Approved folder<select aria-label="Tool folder" value={root} onChange={event => setRoot(event.target.value)}><option value="">Select a folder</option>{Object.entries(policy.roots).map(([id, folder]) => <option key={id} value={id}>{folder}</option>)}</select></label>
        <label>Relative path<input aria-label="Relative tool path" value={path} onChange={event => setPath(event.target.value)} maxLength={500} /></label>
        {tool === 'search_files' && <label>Filename search<input aria-label="Filename search" value={query} onChange={event => setQuery(event.target.value)} maxLength={100} /></label>}
      </>}
      {tool === 'open_application' && <label>Approved application<select aria-label="Approved application" value={application} onChange={event => setApplication(event.target.value)}><option value="">Select an application</option>{policy.applications.map(app => <option key={app} value={app}>{app}</option>)}</select></label>}
      {tool === 'open_website' && <label>Approved website<select aria-label="Approved website" value={website} onChange={event => setWebsite(event.target.value)}><option value="">Select a website</option>{Object.entries(policy.websites).map(([id, url]) => <option key={id} value={id}>{url}</option>)}</select></label>}
      <button type="button" onClick={() => void act(async () => acceptProposal(await api<Operation>('/proposals', 'POST', { tool, arguments: argumentsForTool() })))}>Preview action</button>
    </fieldset>
    {operation && <section aria-label="Tool action preview" className="tool-result"><h3>{operation.tool} · {operation.status}</h3>
      <pre>{JSON.stringify(operation.arguments, null, 2)}</pre>
      {operation.status === 'pending' && <><p>Approve only if the tool and exact inputs match your intention. Approval expires after five minutes. Opening a website may contact the internet; apps may have their own behavior.</p>
        <label><input type="checkbox" checked={actionApproval} onChange={event => setActionApproval(event.target.checked)} /> I approve this exact action</label>
        <button type="button" disabled={!actionApproval || busy} onClick={() => void act(async () => setOperation(await api<Operation>(`/operations/${operation.id}/execute`, 'POST', { approved: true })))}>Run approved action</button></>}
      {active && <button type="button" onClick={() => void act(async () => setOperation(await api<Operation>(`/operations/${operation.id}/cancel`, 'POST')))}>Cancel action</button>}
      {operation.status === 'running' && <p role="status">Action running… Cancellation stops remaining work; it cannot close an app or browser already opened.</p>}
      {operation.error && <p role="alert">{operation.error}</p>}
      {operation.result !== null && <><p>Completed action result. Document text is untrusted data and is not sent to the AI or saved as memory.</p><pre aria-label="Tool result">{JSON.stringify(operation.result, null, 2)}</pre></>}
      {!active && <button type="button" onClick={() => { setOperation(null); setActionApproval(false); }}>Dismiss action result</button>}
    </section>}
    {notice && <p role="status" className="memory-notice">{notice}</p>}
  </details>;
}

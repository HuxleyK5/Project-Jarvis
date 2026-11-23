import { useEffect, useState } from 'react';
import { useAutomation } from '../hooks/useAutomation';
import type { Workflow } from '../services/automation';

const terminal = ['completed', 'failed', 'cancelled', 'blocked', 'expired'];
export default function AutomationPanel({ onActivity }: { onActivity: (text: string, warning: boolean) => void }) {
  const automation = useAutomation(onActivity);
  const { policy, workflows, busy, ready } = automation;
  const [enabled, setEnabled] = useState(false);
  const [automatic, setAutomatic] = useState<string[]>([]);
  const [permissionApproval, setPermissionApproval] = useState(false);
  const [question, setQuestion] = useState('');
  const [selected, setSelected] = useState('');
  const [approved, setApproved] = useState(false);
  const [scheduleApproved, setScheduleApproved] = useState(false);
  const [when, setWhen] = useState('');
  const [manual, setManual] = useState('{"outcome":"Check workstation twice","steps":[{"tool":"system_info","arguments":{}},{"tool":"system_info","arguments":{}}]}');
  const flow = workflows.find(item => item.id === selected) || workflows[0];
  useEffect(() => { setEnabled(policy.enabled); setAutomatic(policy.automatic_tools); setPermissionApproval(false); }, [policy.enabled, policy.automatic_tools.join(',')]);
  useEffect(() => { setApproved(false); setScheduleApproved(false); }, [flow?.id, flow?.status]);
  const choose = (value: Workflow | undefined) => { if (value) setSelected(value.id); };

  return <details className="voice-controls capability-controls automation-controls"><summary>WORKFLOWS · {policy.enabled ? 'SESSION ENABLED' : 'DISABLED'}</summary>
    <p>Describe one outcome to generate up to eight ordered tool steps. Plans never execute just because the AI generated them. First approve folders/apps/sites in COMPUTER TOOLS. A failed or blocked step stops subsequent actions.</p>
    <fieldset disabled={!ready || busy}><legend>Workflow permissions</legend>
      <label><input type="checkbox" checked={enabled} onChange={event => { setEnabled(event.target.checked); setPermissionApproval(false); }} />Enable automation for this backend session</label>
      <p>Automatic: only the low-risk tools you approve below. Confirmation required: other authorized tools, including document reading and app/site opening. Blocked: unknown tools or missing/revoked permissions. The AI cannot change these categories.</p>
      {policy.eligible_automatic_tools.map(tool => <label key={tool}><input type="checkbox" checked={automatic.includes(tool)} onChange={event => { setAutomatic(value => event.target.checked ? [...value, tool] : value.filter(item => item !== tool)); setPermissionApproval(false); }} />Allow automatic {tool}</label>)}
      <label><input type="checkbox" checked={permissionApproval} onChange={event => setPermissionApproval(event.target.checked)} />I approve workflow permissions and local metadata history</label>
      <button type="button" disabled={!permissionApproval} onClick={() => void automation.request('/policy', 'PUT', { enabled, automatic_tools: automatic, approved: true })}>Apply workflow permissions</button>
    </fieldset>
    <div className="voice-actions"><button type="button" disabled={!ready || !policy.enabled || busy} onClick={() => void automation.request('/policy', 'PUT', { enabled: false, automatic_tools: [], approved: true })}>Disable automation and cancel workflows</button></div>
    <fieldset disabled={!ready || !policy.enabled || busy}><legend>Requested outcome</legend>
      <label>Workflow instruction<textarea aria-label="Workflow instruction" maxLength={4000} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Check system information, then list my approved project folder" /></label>
      <button type="button" disabled={!question.trim()} onClick={() => void automation.request<{ workflow: Workflow | null; message?: string }>('/plan', 'POST', { question }).then(value => { if (value?.workflow) choose(value.workflow); else if (value?.message) automation.setNotice(value.message); })}>Generate workflow plan</button>
      <p>Planning uses local Ollama and the approved catalog. No requests, paths, file text or results are written to workflow history.</p>
      <details><summary>Manual structured plan (works without AI)</summary><label>Explicit workflow plan<textarea aria-label="Explicit workflow plan" value={manual} maxLength={16000} onChange={event => setManual(event.target.value)} /></label>
        <button type="button" onClick={() => {
          try { const parsed: unknown = JSON.parse(manual); void automation.request<Workflow>('/plans', 'POST', parsed).then(choose); }
          catch { automation.setNotice('Enter valid JSON. Nothing was executed.'); }
        }}>Preview structured workflow</button></details>
    </fieldset>
    {busy && <div className="voice-actions"><span role="status">Processing workflow request…</span><button type="button" onClick={automation.stopPlanning}>Cancel workflow request</button></div>}
    {workflows.length > 0 && <label>Session workflow<select aria-label="Session workflow" value={flow?.id || ''} onChange={event => setSelected(event.target.value)}>{workflows.map(item => <option key={item.id} value={item.id}>{item.outcome} · {item.status}</option>)}</select></label>}
    {flow && <section className="tool-result" aria-label="Workflow plan"><h3>{flow.outcome} · {flow.status}</h3>
      <p>Completed steps: {flow.report.completed.join(', ') || 'none'}. Incomplete steps: {flow.report.incomplete.join(', ') || 'none'}.</p>
      {flow.scheduled_for && <p>Scheduled: {new Date(flow.scheduled_for).toLocaleString()} ({Intl.DateTimeFormat().resolvedOptions().timeZone})</p>}
      <ol className="workflow-steps">{flow.steps.map(step => <li key={step.number}><strong>{step.tool} · {step.category.replaceAll('_', ' ')} · {step.status}</strong>
        <pre>{JSON.stringify(step.arguments, null, 2)}</pre>
        {step.verification && <p>{step.verification.passed ? 'Verified observable result: ' : 'Verification failed: '}{step.verification.detail}</p>}
        {step.error && <p role="alert">{step.error}</p>}
        {step.result !== null && <details><summary>Step {step.number} result (untrusted text)</summary><pre>{JSON.stringify(step.result, null, 2)}</pre></details>}
      </li>)}</ol>
      {flow.error && <p role="status">{flow.error}</p>}
      {['planned', 'awaiting_confirmation'].includes(flow.status) && <>
        {flow.requires_confirmation ? <label><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} />I approve this exact ordered workflow, including significant actions</label> : <p>All steps qualify for your approved automatic permissions. Starting this plan needs no further confirmation.</p>}
        <button type="button" disabled={busy || (flow.requires_confirmation && !approved)} onClick={() => void automation.request(`/workflows/${flow.id}/start`, 'POST', { approved })}>Start workflow</button>
      </>}
      {!terminal.includes(flow.status) && <button type="button" onClick={() => void automation.cancel(flow.id)}>Cancel workflow</button>}
      {flow.status === 'planned' && <fieldset disabled={!policy.scheduler_available || busy}><legend>Future one-time start</legend>
        <label>Start at (your browser timezone)<input aria-label="Workflow start time" type="datetime-local" value={when} onChange={event => { setWhen(event.target.value); setScheduleApproved(false); }} /></label>
        <label><input type="checkbox" checked={scheduleApproved} onChange={event => setScheduleApproved(event.target.checked)} />I approve this future start time; significant actions will still wait for confirmation when due</label>
        <button type="button" disabled={!when || !scheduleApproved} onClick={() => {
          const time = new Date(when);
          if (Number.isNaN(time.getTime())) { automation.setNotice('Choose a valid future time.'); return; }
          void automation.request(`/workflows/${flow.id}/schedule`, 'POST', { when: time.toISOString(), approved: true });
        }}>Schedule workflow</button>
      </fieldset>}
    </section>}
    <p>Scheduler: {policy.scheduler_available ? 'APScheduler available' : 'APScheduler not installed; immediate workflows work'}. Schedules and permissions reset on backend restart. Cancellation cannot undo completed launches or forcibly interrupt a blocking Windows call.</p>
    <details className="workflow-history"><summary>EXECUTION HISTORY · METADATA ONLY</summary><p>Stored locally in data/workflow-history.jsonl, separately from conversation memory. Latest 100 events; executable plans and results stay in session memory.</p>
      {automation.history.length ? <ol>{automation.history.map((item, index) => <li key={`${item.workflow_id}:${item.time}:${index}`}><time>{new Date(item.time).toLocaleString()}</time> · {item.workflow_id.slice(0, 8)} · {item.status} · {item.completed}/{item.total} complete · {item.tools.join(', ')}</li>)}</ol> : <p>No workflow executions recorded.</p>}
    </details>
    {automation.notice && <p className="memory-notice" role="status">{automation.notice}</p>}
  </details>;
}

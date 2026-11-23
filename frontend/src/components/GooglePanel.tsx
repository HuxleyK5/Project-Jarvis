import { useCallback, useEffect, useRef, useState } from 'react';
import { googleRequest, type GoogleProposal, type GoogleRequest, type GoogleStatus } from '../services/google';
import { CalendarData, ClassroomData, GmailData } from './GoogleData';

function ServiceCard({ status, api, refresh, onActivity }: { status: GoogleStatus; api: GoogleRequest; refresh: () => Promise<void>; onActivity: (text: string, warning: boolean) => void }) {
  const [enabled, setEnabled] = useState(status.enabled);
  const [write, setWrite] = useState(status.write);
  const [send, setSend] = useState(status.send);
  const [role, setRole] = useState(status.role);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [url, setUrl] = useState('');
  const [proposal, setProposal] = useState<GoogleProposal | null>(null);
  const [actionApproved, setActionApproved] = useState(false);
  const [forgetApproved, setForgetApproved] = useState(false);
  const service = status.service;
  useEffect(() => { setEnabled(status.enabled); setWrite(status.write); setSend(status.send); setRole(status.role); setApproved(false); }, [status.enabled, status.write, status.send, status.role]);
  useEffect(() => { if (status.status !== 'authorizing') setUrl(''); }, [status.status]);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setNotice('');
    try { await action(); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Google request failed.'); onActivity(`Google ${service}: request did not complete; inspect integration controls`, true); }
    finally { setBusy(false); await refresh().catch(() => {}); }
  }
  function propose(value: GoogleProposal) { setProposal(value); setActionApproved(false); onActivity(`Google ${service}: ${value.action} proposed; awaiting approval`, false); }
  const connected = ['connected', 'refresh_pending'].includes(status.status);
  const dataProps = { api, status, propose, notice: setNotice, busy, run: (action: () => Promise<void>) => void run(action) };

  return <section className="google-service" aria-label={`Google ${service} integration`}>
    <div className="panel-heading"><h3>GOOGLE {service.toUpperCase()}</h3><span role="status">{status.status === 'connected' ? status.connection_verified ? 'AUTHORIZED · LAST API REQUEST SUCCEEDED' : 'AUTHORIZED · API NOT YET VERIFIED' : status.status.replaceAll('_', ' ').toUpperCase()}</span></div>
    <fieldset disabled={busy}><legend>Capabilities and consent · {service}</legend>
      <label><input type="checkbox" checked={enabled} onChange={event => { setEnabled(event.target.checked); setApproved(false); }} />Enable Google {service}</label>
      {service !== 'classroom' && <label><input type="checkbox" checked={write} onChange={event => { setWrite(event.target.checked); setApproved(false); }} />{service === 'gmail' ? 'Allow creating Gmail drafts' : 'Allow proposed Calendar event creation'}</label>}
      {service === 'gmail' && <><label><input type="checkbox" checked={send} onChange={event => { setSend(event.target.checked); setApproved(false); }} />Allow confirmed Gmail sending</label><p>Google's draft scope also permits sending. JARVIS keeps sending separately disabled unless you enable it here. No delete/modify mailbox capability is exposed.</p></>}
      {service === 'classroom' && <label>Classroom role<select aria-label="Google Classroom role" value={role} onChange={event => { setRole(event.target.value as 'student' | 'teacher'); setApproved(false); }}><option value="student">Student · my coursework</option><option value="teacher">Teacher · coursework in authorized courses</option></select></label>}
      <label><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} />I approve these {service} capabilities and encrypted local OAuth token storage</label>
      <button type="button" disabled={!approved} onClick={() => void run(async () => {
        await api(`/${service}/settings`, 'PUT', { enabled, write, send, role, approved: true }); setProposal(null); setApproved(false); setUrl('');
        onActivity(`Google ${service}: capabilities updated`, false);
      })}>Apply {service} capabilities</button>
    </fieldset>
    <details><summary>Requested OAuth scopes · {service}</summary><ul>{status.requested_scopes.map(scope => <li key={scope}><code>{scope}</code></li>)}</ul><p>Only this service is requested during its consent flow. No account identity/profile scope is requested. Capabilities reset to disabled on backend restart; encrypted tokens remain until disconnected.</p></details>
    {!status.client_configured && <p>OAuth client setup required. Import your own Desktop app client JSON using the offline setup instructions in docs/GOOGLE_INTEGRATIONS.md. Do not paste credentials into chat. No Google account has been connected automatically.</p>}
    <div className="voice-actions"><button type="button" disabled={busy || !status.enabled || !status.client_configured} onClick={() => void run(async () => {
      setProposal(null);
      const result = await api<{ authorization_url: string }>(`/${service}/connect`, 'POST', { approved: true });
      const target = new URL(result.authorization_url);
      if (target.origin !== 'https://accounts.google.com' || target.pathname !== '/o/oauth2/v2/auth') throw new Error('Unexpected Google authorization URL.');
      setUrl(result.authorization_url); onActivity(`Google ${service}: consent link prepared`, false);
    })}>Connect or renew Google {service}</button>
    {status.status === 'authorizing' && <button type="button" disabled={busy} onClick={() => void run(async () => { await api(`/${service}/cancel-auth`, 'POST'); setUrl(''); })}>Cancel {service} authorization</button>}</div>
    {url && <p><a href={url} target="_blank" rel="noopener noreferrer">Open Google consent for {service}</a> · Expires after five minutes. Return here after consent.</p>}
    {status.enabled && !connected && <p>Reading and writes are unavailable until OAuth setup, consent, and the necessary permissions are complete. Reconnect for expired/revoked authorization. School/admin policies and API verification can deny access.</p>}
    {status.enabled && connected && <><p>Saved authorization is available. Google connectivity and actual access are checked when you request data. Disable the integration to stop new requests.</p>
      {service === 'calendar' ? <CalendarData key={`${service}-${status.write}`} {...dataProps} /> : service === 'gmail' ? <GmailData key={`${service}-${status.write}-${status.send}`} {...dataProps} /> : <ClassroomData key={`${service}-${status.role}`} {...dataProps} />}
    </>}
    {proposal && <section className="tool-result" aria-label={`Google ${service} action preview`}><h4>{proposal.action.replaceAll('_', ' ')} · {proposal.status}</h4>
      {proposal.sender && <p>Authorized sender: {proposal.sender}</p>}
      <pre>{JSON.stringify(proposal.payload, null, 2)}</pre><p>This exact snapshot will be used. Editing the compose form does not change it; cancel and create a new proposal to change recipients/content. Approval expires after five minutes.</p>
      {proposal.status === 'pending' && <><label><input type="checkbox" checked={actionApproved} onChange={event => setActionApproved(event.target.checked)} />I confirm this exact Google {proposal.action.replaceAll('_', ' ')} action</label>
        <button type="button" disabled={busy || !actionApproved} onClick={() => void run(async () => {
          try { const value = await api<GoogleProposal>(`/proposals/${proposal.id}/execute`, 'POST', { approved: true }); setProposal(value); onActivity(`Google ${service}: ${value.action} ${value.status}`, false); }
          finally { setProposal(await api<GoogleProposal>(`/proposals/${proposal.id}`).catch(() => ({ ...proposal, status: 'outcome_unknown', error: 'Inspect Google before retrying this external action.' }))); }
        })}>Execute confirmed Google action</button>
        <button type="button" disabled={busy} onClick={() => void run(async () => setProposal(await api<GoogleProposal>(`/proposals/${proposal.id}/cancel`, 'POST')))}>Cancel Google action</button></>}
      {proposal.error && <p role="status">{proposal.error}</p>}{proposal.result !== null && <pre aria-label="Google action result">{JSON.stringify(proposal.result, null, 2)}</pre>}
      {proposal.status !== 'pending' && <button type="button" onClick={() => setProposal(null)}>Dismiss Google action</button>}
    </section>}
    {status.saved_authorization && <div><label><input type="checkbox" checked={forgetApproved} onChange={event => setForgetApproved(event.target.checked)} />I confirm forgetting local {service} authorization</label><button type="button" disabled={busy || !forgetApproved} onClick={() => void run(async () => {
      await api(`/${service}/disconnect`, 'POST', { approved: true }); setProposal(null); setForgetApproved(false); setUrl(''); onActivity(`Google ${service}: disconnected locally`, false);
    })}>Disconnect Google {service} and forget tokens</button><p>Disconnect removes local tokens; review Google Account third-party access to revoke the cloud grant. Revoking the shared OAuth client there can affect the other services.</p></div>}
    {busy && <p role="status">Google request in progress. Started external writes cannot be recalled.</p>}
    {notice && <p className="memory-notice" role="status">{notice}</p>}
  </section>;
}

export default function GooglePanel({ onActivity }: { onActivity: (text: string, warning: boolean) => void }) {
  const token = useRef('');
  const [statuses, setStatuses] = useState<GoogleStatus[]>([]);
  const [notice, setNotice] = useState('');
  const api = useCallback<GoogleRequest>((path, method, body) => googleRequest(token.current, path, method, body), []);
  const refresh = useCallback(async (signal?: AbortSignal) => { const value = await googleRequest<GoogleStatus[]>(token.current, '/status', 'GET', undefined, signal); if (!signal?.aborted) setStatuses(value); }, []);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch('/api/tools/session', { cache: 'no-store', signal: controller.signal });
        const data = await response.json();
        if (!response.ok || typeof data.token !== 'string') throw new Error('Google integration session unavailable. Start the backend and refresh.');
        token.current = data.token; await refresh(controller.signal);
      } catch (error) { if (!controller.signal.aborted) setNotice(error instanceof Error ? error.message : 'Google integrations unavailable.'); }
    })();
    return () => controller.abort();
  }, [refresh]);
  const polling = statuses.some(status => status.enabled);
  useEffect(() => {
    if (!polling) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => void refresh(controller.signal).catch(error => { if (!controller.signal.aborted) setNotice(error.message); }), 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [polling, refresh]);
  return <details className="voice-controls capability-controls google-controls"><summary>GOOGLE PRODUCTIVITY · OPT-IN</summary>
    <p>Calendar, Gmail and Classroom use official Google APIs and independent consent. No account data is loaded automatically. Credentials use Windows-user DPAPI encryption; fetched content stays out of conversation memory. Summaries are explicitly requested through local Ollama. External changes always require an exact preview and confirmation.</p>
    {statuses.map(status => <ServiceCard key={status.service} status={status} api={api} refresh={refresh} onActivity={onActivity} />)}
    {notice && <p role="status" className="memory-notice">{notice}</p>}
  </details>;
}

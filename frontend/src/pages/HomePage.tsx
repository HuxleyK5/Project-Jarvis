import { useEffect, useRef, useState, type FormEvent } from 'react';
import AssistantCore from '../components/AssistantCore';
import Icon from '../components/Icon';
import { useBackend } from '../hooks/useBackend';

interface Message { id: number; text: string; time: Date }
interface Activity { id: number; text: string; time: Date; tone: string }
const timeLabel = (date: Date) => date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

export default function HomePage() {
  const { connection, health, error, checking, lastChecked, retry } = useBackend();
  const [now, setNow] = useState(new Date());
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const sequence = useRef(0);
  const previous = useRef('');
  const logEnd = useRef<HTMLDivElement>(null);
  const online = connection === 'online';
  const status = connection === 'checking' ? 'Connecting' : online ? 'Backend online' : 'Backend offline';

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (connection === 'checking') return;
    const signature = `${connection}:${health?.ai_connected}`;
    if (signature === previous.current) return;
    previous.current = signature;
    const time = new Date();
    const entries: Activity[] = [{ id: ++sequence.current, time, tone: online ? 'good' : 'warn',
      text: online ? 'Local backend connection established' : 'Local backend unavailable' }];
    if (online) entries.push({ id: ++sequence.current, time, tone: 'neutral',
      text: health?.ai_connected ? 'Model reported connected · chat API unavailable' : 'AI model not connected' });
    setActivities(value => [...entries, ...value].slice(0, 50));
  }, [connection, health?.ai_connected, online]);

  useEffect(() => { logEnd.current?.scrollIntoView({ block: 'nearest' }); }, [messages]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const time = new Date();
    setMessages(value => [...value, { id: ++sequence.current, text, time }]);
    setActivities(value => [{ id: ++sequence.current, text: 'Message saved to this session · not sent', time, tone: 'neutral' }, ...value].slice(0, 50));
    setDraft('');
  }

  return (
    <div className="dashboard">
      <aside className="rail" aria-label="Dashboard navigation">
        <a className="brand-mark" href="#overview" aria-label="JARVIS overview">J<span>.</span></a>
        <nav>
          <a className="rail-link selected" href="#overview" aria-label="Overview"><Icon name="grid" /></a>
          <a className="rail-link" href="#conversation" aria-label="Conversation"><Icon name="message" /></a>
          <a className="rail-link" href="#system" aria-label="System information"><Icon name="chip" /></a>
          <a className="rail-link" href="#activity" aria-label="Activity history"><Icon name="clock" /></a>
        </nav>
        <span className="rail-caption">LOCAL<br />V.01</span>
      </aside>

      <div className="workspace" id="overview">
        <header className="topbar">
          <div className="wordmark">J.A.R.V.I.S<span>PERSONAL INTELLIGENCE INTERFACE</span></div>
          <div className="topbar-right">
            <div className={`connection-badge ${connection}`} role="status"><span className="status-dot" />{status}</div>
            <div className="header-time"><strong>{now.toLocaleTimeString([], { hour12: false })}</strong><span>{now.toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' })}</span></div>
          </div>
        </header>

        <main className="dashboard-main">
          <div className="page-heading"><div><p className="eyebrow">COMMAND CENTER / OVERVIEW</p><h1>Your personal command center<span>.</span></h1><p className="subtitle">A clear view of your assistant. Every system, in one place.</p></div><span className="local-tag"><span />LOCAL ENVIRONMENT</span></div>

          <div className="dashboard-grid">
            <section className="panel core-panel" aria-labelledby="core-title">
              <div className="panel-heading"><h2 id="core-title"><Icon name="pulse" size={16} />ASSISTANT CORE</h2><span className="micro-label">JARVIS / 01</span></div>
              <div className="core-stage"><span className="coordinate coordinate-left">SYS.01<br />LOCAL NODE</span><AssistantCore online={online} /><span className="coordinate coordinate-right">NEURAL LINK<br />{health?.ai_connected ? 'CONNECTED' : 'UNAVAILABLE'}</span></div>
              <div className="core-caption"><span className="eyebrow">J.A.R.V.I.S</span><h3>{online ? 'Standing by' : connection === 'checking' ? 'Establishing connection' : 'Awaiting connection'}</h3><p>{health?.ai_connected ? 'Model connected · messaging API not available' : online ? 'Backend ready. AI model not connected.' : 'Waiting for the local backend.'}</p></div>
              <div className="waveform-block"><div className="waveform-meta"><span>AUDIO CHANNEL</span><span><span className="tiny-dot" />INACTIVE</span></div><div className="waveform" aria-label="Audio inactive; no microphone signal"><span className="waveform-line" />{Array.from({ length: 65 }, (_, index) => <i key={index} style={{ height: `${index % 5 === 0 ? 10 : index % 3 === 0 ? 6 : 3}px` }} />)}</div><p>No audio input · Voice capabilities are not implemented</p></div>
              <div className="core-footer"><span><span className={`status-dot ${online ? 'cyan' : 'muted-dot'}`} />{online ? 'API REACHABLE' : 'API NOT VERIFIED'}</span><span>{health?.ai_connected ? 'MODEL CONNECTED' : online ? 'NO MODEL CONNECTED' : 'MODEL STATUS UNKNOWN'}</span></div>
            </section>

            <section className="panel conversation-panel" id="conversation" aria-labelledby="conversation-title">
              <div className="panel-heading"><h2 id="conversation-title"><Icon name="message" size={16} />CONVERSATION</h2><span className="counter">{messages.length.toString().padStart(2, '0')}</span></div>
              <div className="conversation-log" role="log" aria-label="Conversation history" aria-live="polite">
                {messages.length === 0 ? <div className="conversation-empty"><div className="empty-icon"><Icon name="message" size={27} /></div><h3>A space for your thoughts.</h3><p>Type a message below to start your session.</p><span className="notice">AI responses are unavailable until a model and messaging API are connected.</span></div>
                  : messages.map(message => <article className="message" key={message.id}><div className="message-meta"><span><span className="user-avatar">Y</span>YOU</span><time dateTime={message.time.toISOString()}>{timeLabel(message.time)}</time></div><p>{message.text}</p><span className="message-state">Saved locally · Not sent to AI</span></article>)}
                <div ref={logEnd} />
              </div>
              <div className="conversation-footer"><span className="tiny-dot" />SESSION ONLY<span>History clears on refresh</span></div>
            </section>

            <section className="panel system-panel" id="system" aria-labelledby="system-title">
              <div className="panel-heading"><h2 id="system-title"><Icon name="chip" size={16} />SYSTEM STATUS</h2><button className={`icon-button ${checking ? 'is-checking' : ''}`} onClick={retry} disabled={checking} aria-label="Refresh backend status" title="Refresh backend status"><Icon name="refresh" size={16} /></button></div>
              <div className="system-rows">
                <div className="system-row"><span>Backend API</span><strong className={online ? 'text-cyan' : 'text-amber'}><span className="status-dot" />{checking ? 'Checking…' : online ? 'Connected' : 'Offline'}</strong></div>
                <div className="system-row"><span>AI model</span><strong>{online ? health?.ai_connected ? 'Connected' : 'Not connected' : 'Unknown'}</strong></div>
                <div className="system-row"><span>Voice interface</span><strong>Not implemented</strong></div>
                <div className="system-row"><span>Computer control</span><strong>Not implemented</strong></div>
              </div>
              {error && <div className="connection-error" role="alert">{error} Start the backend, then refresh.</div>}
              <div className="hardware-heading"><span>WORKSTATION PROFILE</span><span>PHASE 0 SNAPSHOT</span></div>
              <dl className="hardware-list"><div><dt>PROCESSOR</dt><dd>Intel Core i7-8700K<span>6 cores / 12 threads</span></dd></div><div><dt>GRAPHICS</dt><dd>GeForce GTX 1060<span>6 GiB VRAM</span></dd></div><div><dt>MEMORY</dt><dd>15.93 GiB<span>Installed RAM</span></dd></div></dl>
              <p className="snapshot-note">Hardware report · Nov 13, 2026<br />Live resource telemetry is not available.</p>
              <div className="system-footer"><span>LAST HEALTH CHECK</span><time>{lastChecked ? timeLabel(lastChecked) : 'Pending'}</time></div>
            </section>

            <section className="panel activity-panel" id="activity" aria-labelledby="activity-title"><div className="panel-heading"><h2 id="activity-title"><Icon name="clock" size={16} />ACTIVITY HISTORY</h2><span className="micro-label">THIS SESSION</span></div><div className="activity-list" role="log" aria-label="Activity history">{activities.length === 0 ? <p className="activity-pending">Checking the local backend…</p> : activities.map(activity => <div className="activity-item" key={activity.id}><span className={`activity-dot ${activity.tone}`} /><span>{activity.text}</span><time dateTime={activity.time.toISOString()}>{timeLabel(activity.time)}</time></div>)}</div></section>
          </div>

          <form className="command-bar" onSubmit={submit} aria-label="Command input"><div className="command-entry"><span className="command-symbol" aria-hidden="true">›_</span><label className="sr-only" htmlFor="command">Message JARVIS</label><input id="command" value={draft} onChange={event => setDraft(event.target.value)} maxLength={4000} placeholder="Type a message to JARVIS…" autoComplete="off" /><span className="keyboard-hint">ENTER ↵</span><button className="mic-button" type="button" disabled aria-label="Microphone unavailable: voice is not implemented" title="Voice is not implemented"><Icon name="mic" /></button><button className="send-button" type="submit" disabled={!draft.trim()} aria-label="Save message to session"><span>Save</span><Icon name="arrow" size={18} /></button></div><div className="command-note"><span><span className="tiny-dot" />{online ? 'LOCAL BACKEND CONNECTED' : connection === 'checking' ? 'CHECKING LOCAL BACKEND' : 'LOCAL BACKEND UNAVAILABLE'}</span><span>Text is saved to this session only. AI replies and voice are unavailable.</span></div></form>
          <footer className="page-footer"><span>JARVIS INTERFACE <b>V.0.1</b></span><span>LOCAL FIRST. ALWAYS YOURS.</span></footer>
        </main>
      </div>
    </div>
  );
}

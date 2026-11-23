import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import AssistantCore from '../components/AssistantCore';
import Icon from '../components/Icon';
import { useBackend } from '../hooks/useBackend';
import { useChat } from '../hooks/useChat';
import { useVoice } from '../hooks/useVoice';
import VoiceControls from '../components/VoiceControls';
import { useSpeech } from '../hooks/useSpeech';
import SpeechControls from '../components/SpeechControls';
import { useMemory } from '../hooks/useMemory';
import MemoryPanel from '../components/MemoryPanel';
import { useAssistantPreferences } from '../hooks/useAssistantPreferences';
import AssistantPreferences from '../components/AssistantPreferences';
import ToolPanel from '../components/ToolPanel';
import AutomationPanel from '../components/AutomationPanel';
import GooglePanel from '../components/GooglePanel';

interface Activity { id: number; text: string; time: Date; tone: string }
const timeLabel = (date: Date) => date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

export default function HomePage() {
  const { connection, health, error, checking, lastChecked, retry } = useBackend();
  const [now, setNow] = useState(new Date());
  const [draft, setDraft] = useState('');
  const memory = useMemory();
  const preferences = useAssistantPreferences(memory.ready && memory.settings.enabled);
  const { messages, busy, error: chatError, memoryNotice, summary, summarizedTurns, clearSummary, send, stop, acknowledge } = useChat(
    memory.ready && memory.settings.enabled && memory.settings.save_history, preferences.overridden ? preferences.value : undefined);
  const speech = useSpeech();
  const [voiceConsent, setVoiceConsent] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [activities, setActivities] = useState<Activity[]>([]);
  const sequence = useRef(0);
  const logToolActivity = useCallback((text: string, warning: boolean) => {
    setActivities(value => [{ id: ++sequence.current, text, time: new Date(), tone: warning ? 'warn' : 'good' }, ...value].slice(0, 50));
  }, []);
  const previous = useRef('');
  const logEnd = useRef<HTMLDivElement>(null);
  const online = connection === 'online';
  const voice = useVoice(async text => {
    if (busy || !online) {
      setDraft(text);
      setActivities(value => [{ id: ++sequence.current, time: new Date(), tone: 'neutral', text: 'Speech recognized; text placed in input while chat is unavailable' }, ...value].slice(0, 50));
      return;
    }
    setActivities(value => [{ id: ++sequence.current, time: new Date(), tone: 'good', text: 'Recognized speech submitted to local chat' }, ...value].slice(0, 50));
    speech.stop();
    const answer = await send(text, 'voice');
    if (answer) await speech.speak(answer);
  }, async () => {
    const text = 'Yes, how can I help?';
    acknowledge(text);
    await speech.speak(text);
  }, speech.active);
  function startVoice() { speech.stop(); void voice.start(voiceConsent, continuous); }
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
      text: health?.ai_connected ? `Local model available: ${health.model ?? 'Ollama'}` : health?.ai_message ?? 'AI model not connected' });
    setActivities(value => [...entries, ...value].slice(0, 50));
  }, [connection, health?.ai_connected, health?.ai_message, health?.model, online]);

  useEffect(() => {
    if (chatError) setActivities(value => [{ id: ++sequence.current, time: new Date(), tone: 'warn', text: chatError }, ...value].slice(0, 50));
  }, [chatError]);

  useEffect(() => { logEnd.current?.scrollIntoView({ block: 'nearest' }); }, [messages]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || !online) return;
    if (voice.active) voice.stop();
    speech.stop();
    const time = new Date();
    void send(text).then(answer => { if (answer) return speech.speak(answer); });
    setActivities(value => [{ id: ++sequence.current, text: 'Chat request submitted to local backend', time, tone: 'neutral' }, ...value].slice(0, 50));
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
              <div className="core-caption"><span className="eyebrow">J.A.R.V.I.S</span><h3>{speech.state === 'playing' ? 'Speaking' : busy ? 'Preparing your response' : online ? 'Standing by' : connection === 'checking' ? 'Establishing connection' : 'Awaiting connection'}</h3><p>{health?.ai_connected ? `Local conversation · ${health.model ?? 'Ollama'}` : online ? 'Backend ready. AI model not connected.' : 'Waiting for the local backend.'}</p></div>
              <div className="waveform-block"><div className="waveform-meta"><span>AUDIO CHANNEL</span><span><span className="tiny-dot" />{speech.active ? speech.state.toUpperCase() : voice.active ? voice.state.toUpperCase() : 'INACTIVE'}</span></div><div className="waveform" aria-label={speech.active ? "Speech playback waveform" : voice.active ? "Live microphone level" : "Audio inactive; no microphone signal"}><span className="waveform-line" />{Array.from({ length: 65 }, (_, index) => <i key={index} style={{ height: `${(speech.active || voice.active) ? 3 + Math.min(25, (speech.active ? speech.level : voice.level) * 180) * (0.4 + (index % 5) / 6) : index % 5 === 0 ? 10 : index % 3 === 0 ? 6 : 3}px` }} />)}</div><p>{speech.active ? 'Local speech output - Microphone forwarding paused' : voice.active ? 'Microphone active - Local processing - No audio files' : 'Microphone off - Enable voice input below'}</p></div>
              <div className="core-footer"><span><span className={`status-dot ${online ? 'cyan' : 'muted-dot'}`} />{online ? 'API REACHABLE' : 'API NOT VERIFIED'}</span><span>{health?.ai_connected ? 'MODEL CONNECTED' : online ? 'NO MODEL CONNECTED' : 'MODEL STATUS UNKNOWN'}</span></div>
            </section>

            <section className="panel conversation-panel" id="conversation" aria-labelledby="conversation-title">
              <div className="panel-heading"><h2 id="conversation-title"><Icon name="message" size={16} />CONVERSATION</h2><span className="counter">{messages.length.toString().padStart(2, '0')}</span></div>
              <div className="conversation-log" role="log" aria-label="Conversation history" aria-live="polite">
                {messages.length === 0 ? <div className="conversation-empty"><div className="empty-icon"><Icon name="message" size={27} /></div><h3>A space for your thoughts.</h3><p>Type a message below to start your session.</p><span className="notice">{health?.ai_connected ? `Ready to talk with ${health.model ?? 'your local model'}. Recent completed turns provide follow-up context.` : health?.ai_message ?? 'Checking the local AI provider. No model is downloaded automatically.'}</span></div>
                  : messages.map(message => <article className={`message message-${message.role}`} key={message.id}><div className="message-meta"><span><span className="user-avatar">{message.role === 'user' ? 'Y' : 'J'}</span>{message.role === 'user' ? message.source === 'voice' ? 'YOU · VOICE' : 'YOU' : 'JARVIS'}</span><time dateTime={message.time.toISOString()}>{timeLabel(message.time)}</time></div><p>{message.text}</p><span className="message-state">{message.state === 'sending' ? message.role === 'assistant' ? 'Streaming response…' : 'Awaiting local AI…' : message.state === 'complete' ? message.acknowledgement ? 'Wake acknowledgement' : message.role === 'assistant' ? 'Local AI · Complete' : 'Sent to local AI' : message.state === 'stopped' ? 'Stopped · Excluded from context' : 'Incomplete · Excluded from context'}</span></article>)}
                {busy && <div className="chat-progress" role="status">{messages.some(message => message.role === 'assistant' && message.state === 'sending') ? 'JARVIS is responding…' : 'Waiting for Ollama. The model may be loading…'}</div>}
                {chatError && <div className="connection-error chat-error" role="alert">{chatError}</div>}
                {memoryNotice && <p className="memory-notice" role="status">{memoryNotice}</p>}
                <div ref={logEnd} />
              </div>
              <div className="conversation-footer"><span className="tiny-dot" />SESSION ONLY<span>Live chat clears on refresh</span></div>
            </section>

            <section className="panel system-panel" id="system" aria-labelledby="system-title">
              <div className="panel-heading"><h2 id="system-title"><Icon name="chip" size={16} />SYSTEM STATUS</h2><button className={`icon-button ${checking ? 'is-checking' : ''}`} onClick={retry} disabled={checking} aria-label="Refresh backend status" title="Refresh backend status"><Icon name="refresh" size={16} /></button></div>
              <div className="system-rows">
                <div className="system-row"><span>Backend API</span><strong className={online ? 'text-cyan' : 'text-amber'}><span className="status-dot" />{checking ? 'Checking…' : online ? 'Connected' : 'Offline'}</strong></div>
                <div className="system-row"><span>AI model</span><strong>{online ? health?.ai_connected ? 'Connected' : 'Not connected' : 'Unknown'}</strong></div>
                {online && health?.model && <div className="system-row"><span>Selected model</span><strong>{health.model}</strong></div>}
                <div className="system-row"><span>Voice input</span><strong>{voice.active ? voice.state : 'Off · Opt-in'}</strong></div>
                <div className="system-row"><span>Computer control</span><strong>Approval required</strong></div>
              </div>
              {error && <div className="connection-error" role="alert">{error} Start the backend, then refresh.</div>}
              {online && !health?.ai_connected && health?.ai_message && <div className="connection-error" role="status">{health.ai_message}</div>}
              <div className="hardware-heading"><span>WORKSTATION PROFILE</span><span>PHASE 0 SNAPSHOT</span></div>
              <dl className="hardware-list"><div><dt>PROCESSOR</dt><dd>Intel Core i7-8700K<span>6 cores / 12 threads</span></dd></div><div><dt>GRAPHICS</dt><dd>GeForce GTX 1060<span>6 GiB VRAM</span></dd></div><div><dt>MEMORY</dt><dd>15.93 GiB<span>Installed RAM</span></dd></div></dl>
              <p className="snapshot-note">Hardware report · Nov 13, 2026<br />Live resource telemetry is not available.</p>
              <div className="system-footer"><span>LAST HEALTH CHECK</span><time>{lastChecked ? timeLabel(lastChecked) : 'Pending'}</time></div>
            </section>

            <section className="panel activity-panel" id="activity" aria-labelledby="activity-title"><div className="panel-heading"><h2 id="activity-title"><Icon name="clock" size={16} />ACTIVITY HISTORY</h2><span className="micro-label">THIS SESSION</span></div><div className="activity-list" role="log" aria-label="Activity history">{activities.length === 0 ? <p className="activity-pending">Checking the local backend…</p> : activities.map(activity => <div className="activity-item" key={activity.id}><span className={`activity-dot ${activity.tone}`} /><span>{activity.text}</span><time dateTime={activity.time.toISOString()}>{timeLabel(activity.time)}</time></div>)}</div></section>
          </div>

          <VoiceControls state={voice.state} error={voice.error} transcript={voice.transcript}
            consent={voiceConsent} continuous={continuous} unavailable={!online || busy}
            setConsent={value => { if (!value) voice.stop(); setVoiceConsent(value); }}
            setContinuous={value => { voice.stop(); setContinuous(value); }}
            start={startVoice} stop={voice.stop} finish={voice.finish} />

          <SpeechControls speech={speech} />
          <MemoryPanel memory={memory} />
          <ToolPanel onActivity={logToolActivity} />
          <AutomationPanel onActivity={logToolActivity} />
          <GooglePanel onActivity={logToolActivity} />
          <AssistantPreferences preferences={preferences} memoryEnabled={memory.ready && memory.settings.enabled} />
          <details className="voice-controls session-context"><summary>SESSION CONTEXT {summarizedTurns ? ` · ${summarizedTurns} older exchanges summarized` : ''}</summary>
            <p>Recent completed turns stay in context. Older turns are condensed into bounded source-labelled quotes, not verified facts. Initial context anchors and recent summary quotes are retained; some detail is omitted. This summary stays in browser memory and is never saved as an approved fact or archived with chat.</p>
            {summary ? <><pre>{summary}</pre><div className="voice-actions"><button type="button" disabled={busy} onClick={clearSummary}>Clear older session summary</button></div></> : <p>No older-session summary yet.</p>}
          </details>
          {memory.ready && memory.settings.save_history && <p className="memory-banner" role="status">History saving is ON. New completed text exchanges will be stored locally. Open memory controls to disable it.</p>}

          <form className="command-bar" onSubmit={submit} aria-label="Command input"><div className="command-entry"><span className="command-symbol" aria-hidden="true">›_</span><label className="sr-only" htmlFor="command">Message JARVIS</label><input id="command" value={draft} onChange={event => setDraft(event.target.value)} maxLength={4000} placeholder="Type a message to JARVIS…" autoComplete="off" /><span className="keyboard-hint">ENTER ↵</span><button className="mic-button" type="button" onClick={() => voice.active ? voice.stop() : startVoice()} disabled={!voice.active && (!online || busy)} aria-label={voice.active ? "Stop microphone" : "Start microphone"} title="Microphone capture requires session consent"><Icon name="mic" /></button>{busy && <button className="stop-button" type="button" onClick={stop} aria-label="Stop response">Stop</button>}<button className="send-button" type="submit" disabled={!draft.trim() || busy || !online} aria-label="Send message to JARVIS"><span>Send</span><Icon name="arrow" size={18} /></button></div><div className="command-note"><span><span className="tiny-dot" />{online ? 'LOCAL BACKEND CONNECTED' : connection === 'checking' ? 'CHECKING LOCAL BACKEND' : 'LOCAL BACKEND UNAVAILABLE'}</span><span>Local AI conversation - Voice input and speech output are opt-in</span></div></form>
          <footer className="page-footer"><span>JARVIS INTERFACE <b>V.0.1</b></span><span>LOCAL FIRST. ALWAYS YOURS.</span></footer>
        </main>
      </div>
    </div>
  );
}

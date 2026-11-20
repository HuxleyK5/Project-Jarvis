import { useState, type FormEvent } from 'react';
import type { useMemory } from '../hooks/useMemory';
import type { SavedMemory } from '../services/memory';

export default function MemoryPanel({ memory }: { memory: ReturnType<typeof useMemory> }) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<SavedMemory['kind']>('preference');
  const [content, setContent] = useState('');
  const [approved, setApproved] = useState(false);
  const [editing, setEditing] = useState<number | undefined>();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await memory.save(kind, content, approved, editing)) { setContent(''); setApproved(false); setEditing(undefined); }
  }
  return <details className="voice-controls memory-panel" onToggle={event => { if (event.currentTarget.open) void memory.load(query); }}>
    <summary>SAVED MEMORY &amp; CONVERSATIONS <span>{memory.ready ? memory.settings.enabled ? 'ENABLED' : 'DISABLED' : 'UNAVAILABLE / CHECKING'}</span></summary>
    <p>SQLite memory is local and separate from this temporary chat. Only entries you approve are saved as preferences, projects, or facts. Approved entries may be supplied to the local AI as reference. Disabling stops saving/retrieval; it does not erase saved data.</p>
    <label><input type="checkbox" aria-label="Enable persistent memory" checked={memory.settings.enabled} disabled={!memory.ready || memory.busy || !memory.settings.allowed} onChange={event => void memory.configure(event.target.checked, false)} />Enable persistent memory and use approved entries in conversations</label>
    <label><input type="checkbox" aria-label="Save future conversation history" checked={memory.settings.save_history} disabled={!memory.settings.enabled || memory.busy} onChange={event => void memory.configure(true, event.target.checked)} />Save future completed question/answer pairs to local history until I turn this off (including after restarts)</label>
    <p>Never enter passwords, keys, tokens, or other authentication data. Detected sensitive text is rejected or its entire conversation turn skipped; detection is conservative and imperfect. History saves only new completed pairs, not past chat, failed replies, raw microphone audio, or wake acknowledgements.</p>
    <label><input type="checkbox" aria-label="Recall previous conversations" checked={Boolean(memory.settings.recall_history)} disabled={!memory.settings.enabled || memory.busy} onChange={event => void memory.configure(true, memory.settings.save_history, event.target.checked)} />Allow relevant saved conversation excerpts to be recalled when I refer to previous chats (off by default)</label>
    <form className="memory-search" onSubmit={event => { event.preventDefault(); void memory.load(query); }}>
      <label>Search saved memories and conversation history<input aria-label="Search saved memory and history" value={query} maxLength={200} onChange={event => setQuery(event.target.value)} /></label>
      <button type="submit" disabled={memory.busy}>Search saved data</button>
    </form>
    <form className="memory-form" onSubmit={event => void submit(event)}>
      <h3>{editing === undefined ? 'Approve a new memory' : 'Review edited memory'}</h3>
      <label>Memory category<select aria-label="Memory category" value={kind} onChange={event => { setKind(event.target.value as SavedMemory['kind']); setApproved(false); }}><option value="preference">Preference</option><option value="project">Important project</option><option value="fact">Useful fact</option></select></label>
      <label>Exact text to save<textarea aria-label="Exact memory text" value={content} maxLength={2000} rows={3} onChange={event => { setContent(event.target.value); setApproved(false); }} /></label>
      <label><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} />I reviewed this exact text, approve saving it locally, and confirm it contains no credentials or sensitive personal data.</label>
      <button type="submit" disabled={!memory.settings.enabled || memory.busy || !approved || !content.trim()}>{editing === undefined ? 'Approve and save memory' : 'Approve and update memory'}</button>
      {editing !== undefined && <button type="button" onClick={() => { setEditing(undefined); setContent(''); setApproved(false); }}>Cancel edit</button>}
    </form>
    {memory.error && <p className="voice-error memory-error">{memory.error}</p>}
    <h3>Saved memories</h3>
    <div className="saved-list">{!memory.entries.length ? <p>No saved memories match this view.</p> : memory.entries.map(item => <article className="saved-memory" key={item.id}>
      <span className="micro-label">{item.kind.toUpperCase()}</span><p>{item.content}</p>
      <button type="button" disabled={memory.busy || !memory.settings.enabled} onClick={() => { setEditing(item.id); setKind(item.kind); setContent(item.content); setApproved(false); }}>Edit memory</button>
      <button type="button" disabled={memory.busy} onClick={() => void memory.remove('entries', item.id)}>Delete memory</button>
    </article>)}</div>
    <h3>Saved conversation history</h3>
    <p>Archives are not promoted to approved facts. Model recall requires the separate permission above and a reference to earlier conversations. Up to 100 matches are shown.</p>
    <div className="saved-list">{!memory.turns.length ? <p>No saved conversation turns match this view.</p> : memory.turns.map(turn => <article className="saved-turn" key={turn.id}>
      <time dateTime={turn.created_at}>{new Date(turn.created_at).toLocaleString()}</time>
      <p><strong>You:</strong> {turn.user_text}</p><p><strong>JARVIS:</strong> {turn.assistant_text}</p>
      <button type="button" disabled={memory.busy} onClick={() => void memory.remove('conversations', turn.id)}>Delete saved exchange</button>
    </article>)}</div>
  </details>;
}

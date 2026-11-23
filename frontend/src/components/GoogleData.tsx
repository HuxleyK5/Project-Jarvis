import { useState } from 'react';
import type { GoogleProposal, GoogleRequest, GoogleStatus } from '../services/google';

interface DataProps { api: GoogleRequest; status: GoogleStatus; propose: (value: GoogleProposal) => void; notice: (value: string) => void; busy: boolean; run: (action: () => Promise<void>) => void }
interface Event { id: string; summary?: string; description?: string; start?: { dateTime?: string; date?: string }; end?: { dateTime?: string; date?: string } }
export function CalendarData({ api, status, propose, busy, run }: DataProps) {
  const [events, setEvents] = useState<Event[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [more, setMore] = useState(false);
  const [title, setTitle] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [description, setDescription] = useState('');
  return <div><div className="voice-actions"><button type="button" disabled={busy} onClick={() => run(async () => {
    const data = await api<{ events: Event[]; has_more: boolean }>('/calendar/events'); setEvents(data.events); setMore(data.has_more); setLoaded(true);
  })}>Load upcoming Google events</button></div><p>Primary calendar · next 30 days · at most 50 events. All-day events retain their date.</p>
    {loaded && (events.length ? <ul className="google-items">{events.map(event => <li key={event.id}><strong>{event.summary || '(untitled event)'}</strong><p>{event.start?.dateTime ? new Date(event.start.dateTime).toLocaleString() : event.start?.date || 'Start unavailable'} → {event.end?.dateTime ? new Date(event.end.dateTime).toLocaleString() : event.end?.date || 'End unavailable'}</p>{event.description && <p>{event.description}</p>}</li>)}</ul> : <p>No upcoming events returned.</p>)}
    {more && <p>More events exist beyond this bounded view. Use Google Calendar for the full calendar.</p>}
    <fieldset disabled={busy || !status.write}><legend>Propose an event · primary calendar</legend>
      <label>Event title<input aria-label="Google event title" maxLength={200} value={title} onChange={event => setTitle(event.target.value)} /></label>
      <label>Start (browser timezone)<input aria-label="Google event start" type="datetime-local" value={start} onChange={event => setStart(event.target.value)} /></label>
      <label>End (browser timezone)<input aria-label="Google event end" type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} /></label>
      <label>Description<textarea aria-label="Google event description" maxLength={4000} value={description} onChange={event => setDescription(event.target.value)} /></label>
      <button type="button" disabled={!title.trim() || !start || !end} onClick={() => run(async () => propose(await api<GoogleProposal>('/calendar/proposals', 'POST', { title, start: new Date(start).toISOString(), end: new Date(end).toISOString(), description })))}>Preview Google event</button>
    </fieldset></div>;
}

interface Mail { id: string; thread_id: string; subject: string; from: string; to: string; date: string; text: string; snippet: string; plain_text_available: boolean }
export function GmailData({ api, status, propose, busy, run }: DataProps) {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<{ id: string; threadId: string }[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [mail, setMail] = useState<Mail | null>(null);
  const [thread, setThread] = useState<Mail[]>([]);
  const [summary, setSummary] = useState('');
  const [summaryConsent, setSummaryConsent] = useState(false);
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  async function search(page?: string) {
    const data = await api<{ messages: { id: string; threadId: string }[]; next_page_token: string | null }>(`/gmail/messages?q=${encodeURIComponent(query)}${page ? `&page_token=${encodeURIComponent(page)}` : ''}`);
    setMessages(value => page ? [...value, ...data.messages] : data.messages); setNext(data.next_page_token); setLoaded(true);
  }
  function mailPayload() { return { to: to.split(',').map(value => value.trim()).filter(Boolean), subject, body }; }
  return <div><label>Gmail search<input aria-label="Gmail search" maxLength={500} value={query} onChange={event => { setQuery(event.target.value); setNext(null); }} placeholder="Google search syntax, e.g. newer_than:7d" /></label>
    <button type="button" disabled={busy} onClick={() => run(() => search())}>Search authorized Gmail</button><p>Search returns message IDs. Select one to read its authorized content; attachments and remote images are not downloaded.</p>
    {loaded && !messages.length && <p>No messages returned.</p>}
    <ul className="google-items">{messages.map(item => <li key={item.id}><button type="button" disabled={busy} onClick={() => run(async () => { setMail(await api<Mail>(`/gmail/messages/${encodeURIComponent(item.id)}`)); setThread([]); setSummary(''); setSummaryConsent(false); })}>Read message {item.id}</button></li>)}</ul>
    {next && <button type="button" disabled={busy} onClick={() => run(() => search(next))}>Load more Gmail matches</button>}
    {mail && <section aria-label="Selected Google email"><h4>{mail.subject}</h4><p>From: {mail.from}<br />To: {mail.to}<br />{mail.date}</p><pre>{mail.text || mail.snippet || 'No readable plain-text excerpt available.'}</pre>
      {!mail.plain_text_available && <p>Plain-text body unavailable. Showing a snippet, not a complete HTML email.</p>}
      <button type="button" disabled={busy} onClick={() => run(async () => { const data = await api<{ messages: Mail[] }>(`/gmail/threads/${encodeURIComponent(mail.thread_id)}`); setThread(data.messages); setSummary(''); })}>Read selected conversation</button>
      {thread.map(item => <article key={item.id}><strong>{item.subject} · {item.from}</strong><pre>{item.text || item.snippet}</pre></article>)}
      <label><input type="checkbox" checked={summaryConsent} onChange={event => setSummaryConsent(event.target.checked)} />I approve sending this selected conversation to local Ollama for a summary</label>
      <button type="button" disabled={busy || !summaryConsent} onClick={() => run(async () => { const data = await api<{ summary: string }>(`/gmail/threads/${encodeURIComponent(mail.thread_id)}/summarize`, 'POST', { approved: true }); setSummary(data.summary); })}>Summarize selected Gmail conversation locally</button>
      {summary && <div aria-label="Local email summary"><h4>Local AI summary · review against the source</h4><p>{summary}</p></div>}
    </section>}
    <fieldset disabled={busy || (!status.write && !status.send)}><legend>Compose plain-text email</legend>
      <label>Recipients (comma-separated bare addresses)<input aria-label="Google email recipients" value={to} onChange={event => setTo(event.target.value)} maxLength={2550} /></label>
      <label>Subject<input aria-label="Google email subject" value={subject} onChange={event => setSubject(event.target.value)} maxLength={200} /></label>
      <label>Body<textarea aria-label="Google email body" value={body} onChange={event => setBody(event.target.value)} maxLength={20000} /></label>
      <button type="button" disabled={!status.write || !to.trim() || !subject.trim() || !body.trim()} onClick={() => run(async () => propose(await api<GoogleProposal>('/gmail/proposals/create_draft', 'POST', mailPayload())))}>Preview Gmail draft</button>
      <button type="button" disabled={!status.send || !to.trim() || !subject.trim() || !body.trim()} onClick={() => run(async () => propose(await api<GoogleProposal>('/gmail/proposals/send_message', 'POST', mailPayload())))}>Preview Gmail send</button>
      <p>Creating a draft writes to Gmail. Sending is a separate exact-content proposal; it sends a new message, without silently using a remotely edited draft.</p>
    </fieldset></div>;
}

interface Course { id: string; name: string; section?: string }
interface Assignment { id: string; title: string; description?: string; dueDate?: { year: number; month: number; day: number }; dueTime?: { hours?: number; minutes?: number; seconds?: number } }
function due(item: Assignment) {
  const date = item.dueDate;
  if (!date) return 'No due date provided';
  if (!item.dueTime) return `${date.year}-${String(date.month).padStart(2, '0')}-${String(date.day).padStart(2, '0')} (time unavailable)`;
  const time = item.dueTime;
  return new Date(Date.UTC(date.year, date.month - 1, date.day, time.hours || 0, time.minutes || 0, time.seconds || 0)).toLocaleString();
}
export function ClassroomData({ api, busy, run }: DataProps) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [groups, setGroups] = useState<Record<string, { items: Assignment[]; next: string | null }>>({});
  async function load(page?: string) {
    const data = await api<{ courses: Course[]; next_page_token: string | null }>(`/classroom/courses${page ? `?page_token=${encodeURIComponent(page)}` : ''}`);
    setCourses(value => page ? [...value, ...data.courses] : data.courses); setNext(data.next_page_token); setLoaded(true);
  }
  async function assignments(id: string, page?: string) {
    const data = await api<{ assignments: Assignment[]; next_page_token: string | null }>(`/classroom/courses/${encodeURIComponent(id)}/assignments${page ? `?page_token=${encodeURIComponent(page)}` : ''}`);
    setGroups(value => ({ ...value, [id]: { items: page ? [...value[id].items, ...data.assignments] : data.assignments, next: data.next_page_token } }));
  }
  return <div><button type="button" disabled={busy} onClick={() => run(() => load())}>Load available Classroom courses</button>
    <p>Read-only active courses and published coursework. School administrator policies and your student/teacher role can limit access. Missing dates remain unknown.</p>
    {loaded && !courses.length && <p>No accessible active courses returned.</p>}
    {courses.map(course => <section className="google-course" key={course.id}><h4>{course.name}{course.section ? ` · ${course.section}` : ''}</h4>
      <button type="button" disabled={busy} onClick={() => run(() => assignments(course.id))}>Load assignments for {course.name}</button>
      {groups[course.id] && (groups[course.id].items.length ? <ul className="google-items">{groups[course.id].items.map(item => <li key={item.id}><strong>{item.title}</strong><p>Due: {due(item)}</p>{item.description && <p>{item.description}</p>}</li>)}</ul> : <p>No available published assignments returned.</p>)}
      {groups[course.id]?.next && <button type="button" disabled={busy} onClick={() => run(() => assignments(course.id, groups[course.id].next!))}>Load more assignments for {course.name}</button>}
    </section>)}
    {next && <button type="button" disabled={busy} onClick={() => run(() => load(next))}>Load more Classroom courses</button>}
  </div>;
}

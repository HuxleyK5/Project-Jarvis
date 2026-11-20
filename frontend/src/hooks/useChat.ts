import { useEffect, useRef, useState } from 'react';
import { streamChat, type Turn } from '../services/chat';
import { compressTurns, renderSummary, type SummaryCard } from '../services/context';
import type { AssistantPreferences } from './useAssistantPreferences';

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  time: Date;
  state: 'sending' | 'complete' | 'failed' | 'stopped';
  source?: 'text' | 'voice';
  acknowledgement?: boolean;
}

export function useChat(saveHistory = false, preferences?: AssistantPreferences) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const history = useRef<Turn[]>([]);
  const sequence = useRef(0);
  const mounted = useRef(true);
  const conversation = useRef(crypto.randomUUID());
  const [memoryNotice, setMemoryNotice] = useState('');
  const older = useRef<SummaryCard[]>([]);
  const [summary, setSummary] = useState('');
  const [summarizedTurns, setSummarizedTurns] = useState(0);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; controller.current?.abort(); };
  }, []);

  async function send(text: string, source: 'text' | 'voice' = 'text') {
    if (controller.current || !text.trim()) return;
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError(null);
    setMemoryNotice('');
    const user: ChatMessage = { id: ++sequence.current, role: 'user', text, time: new Date(), state: 'sending', source };
    const assistantId = ++sequence.current;
    setMessages(value => [...value, user]);
    let answer = '';
    let timedOut = false;
    const timer = window.setTimeout(() => { timedOut = true; current.abort(); }, 180000);
    try {
      await streamChat([...history.current, { role: 'user', content: text }], current.signal, delta => {
        answer += delta;
        if (!mounted.current) return;
        setMessages(value => value.some(message => message.id === assistantId)
          ? value.map(message => message.id === assistantId ? { ...message, text: answer } : message)
          : [...value, { id: assistantId, role: 'assistant', text: answer, time: new Date(), state: 'sending' }]);
      }, saveHistory ? { conversation_id: conversation.current, turn_id: crypto.randomUUID(), save_history: true,
        onStatus: status => setMemoryNotice(({ saved: 'This completed exchange was saved to local SQLite history.',
          duplicate: 'This exchange was already saved; no duplicate was created.',
          skipped_sensitive: 'This entire exchange was NOT saved: potentially sensitive content was detected.',
          disabled: 'This exchange was not saved because history storage is disabled.',
          error: 'The AI replied, but local history storage failed. This exchange was not saved.' } as Record<string, string>)[status] || 'History save status is unknown.') } : undefined,
          { summary: renderSummary(older.current), preferences });
      history.current.push({ role: 'user', content: text }, { role: 'assistant', content: answer });
      while (history.current.length > 20 || history.current.reduce((sum, turn) => sum + turn.content.length, 0) > 30000) {
        const removed = history.current.splice(0, 2);
        older.current = compressTurns(older.current, removed);
        setSummarizedTurns(value => value + 1);
        setSummary(renderSummary(older.current));
      }
      if (mounted.current) setMessages(value => value.map(message => message.id === user.id || message.id === assistantId ? { ...message, state: 'complete' } : message));
      return answer;
    } catch (reason) {
      if (mounted.current) {
        const stopped = current.signal.aborted && !timedOut;
        setError(stopped ? 'Response stopped. This incomplete turn is excluded from future context.'
          : timedOut ? 'The response timed out. Check Ollama and try a shorter message.'
          : reason instanceof Error ? reason.message : 'Could not complete the AI response.');
        setMessages(value => value.map(message => message.id === user.id || message.id === assistantId
          ? { ...message, state: stopped ? 'stopped' : 'failed' } : message));
      }
    } finally {
      window.clearTimeout(timer);
      controller.current = null;
      if (mounted.current) setBusy(false);
    }
  }

  function acknowledge(text: string) {
    setMessages(value => [...value, { id: ++sequence.current, role: 'assistant', text, time: new Date(), state: 'complete', acknowledgement: true }]);
  }
  function clearSummary() {
    if (!window.confirm('Forget the extractive summary of older session turns? Saved SQLite memories and recent chat are unchanged.')) return;
    older.current = []; setSummary(''); setSummarizedTurns(0);
  }
  return { messages, busy, error, memoryNotice, summary, summarizedTurns, clearSummary, send, acknowledge, stop: () => controller.current?.abort() };
}

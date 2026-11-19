import { useEffect, useRef, useState } from 'react';
import { streamChat, type Turn } from '../services/chat';

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  time: Date;
  state: 'sending' | 'complete' | 'failed' | 'stopped';
  source?: 'text' | 'voice';
  acknowledgement?: boolean;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const history = useRef<Turn[]>([]);
  const sequence = useRef(0);
  const mounted = useRef(true);
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
      });
      history.current.push({ role: 'user', content: text }, { role: 'assistant', content: answer });
      while (history.current.length > 20 || history.current.reduce((sum, turn) => sum + turn.content.length, 0) > 30000) {
        history.current.splice(0, 2);
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
  return { messages, busy, error, send, acknowledge, stop: () => controller.current?.abort() };
}

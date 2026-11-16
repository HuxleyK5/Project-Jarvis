export interface Turn { role: 'user' | 'assistant'; content: string }

export async function streamChat(messages: Turn[], signal: AbortSignal, onDelta: (text: string) => void): Promise<void> {
  const response = await fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }), signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.error?.message === 'string' ? data.error.message : `Chat failed (HTTP ${response.status}).`);
  }
  if (!response.body || !response.headers.get('content-type')?.includes('application/x-ndjson')) {
    throw new Error('The backend did not return a chat stream.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let received = false;
  function consume(line: string): boolean {
    if (!line.trim()) return false;
    const event = JSON.parse(line);
    if (event.type === 'error') throw new Error(event.error?.message || 'The AI response was interrupted.');
    if (event.type === 'delta' && typeof event.content === 'string') {
      received ||= Boolean(event.content);
      onDelta(event.content);
      return false;
    }
    if (event.type === 'done' && received) return true;
    throw new Error('Invalid or empty response from the AI backend.');
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 1000000) throw new Error('AI response exceeded the stream buffer limit.');
      let index: number;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(index + 1);
        if (consume(line)) return;
      }
      if (done) {
        if (buffer.trim() && consume(buffer)) return;
        throw new Error('The response ended before completion. Please try again.');
      }
    }
  } finally {
    // Also close the connection on malformed/error events instead of leaving generation running.
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

import type { Turn } from './chat';

export interface SummaryCard { role: 'user' | 'assistant'; quote: string }
export function compressTurns(previous: SummaryCard[], turns: Turn[]): SummaryCard[] {
  // Extractive source quotes, never generated claims or persistent storage.
  const added = turns.map(turn => ({ role: turn.role, quote: turn.content.length > 220 ? turn.content.slice(0, 217) + '…' : turn.content }));
  const combined = [...previous, ...added];
  return combined.length <= 16 ? combined : [...combined.slice(0, 2), ...combined.slice(-14)];
}
export function renderSummary(cards: SummaryCard[]): string {
  return cards.map(card => `${card.role === 'user' ? 'User stated' : 'Assistant previously replied (unverified)'}: ${card.quote}`).join('\n').slice(0, 4500);
}

import { useEffect, useRef, useState } from 'react';
import { memoryRequest } from '../services/memory';

export interface AssistantPreferences { tone: 'professional' | 'friendly' | 'formal'; detail: 'balanced' | 'concise' | 'detailed' }
const defaults: AssistantPreferences = { tone: 'professional', detail: 'balanced' };
export function useAssistantPreferences(memoryEnabled: boolean) {
  const [value, setValue] = useState<AssistantPreferences>(defaults);
  const [overridden, setOverridden] = useState(false);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('Applies to this browser session; nothing saved.');
  const revision = useRef(0);
  useEffect(() => {
    const version = ++revision.current;
    setValue(defaults); setOverridden(false); setApproved(false);
    setNotice('Applies to this browser session; nothing saved.');
    if (memoryEnabled) void memoryRequest<AssistantPreferences>('personality').then(profile => {
      if (!profile || !['professional', 'friendly', 'formal'].includes(profile.tone) || !['balanced', 'concise', 'detailed'].includes(profile.detail)) throw new Error('Invalid saved style');
      if (version === revision.current) { setValue(profile); setNotice('Using approved saved style, or defaults if none was saved.'); }
    }).catch(() => { if (version === revision.current) setNotice('Saved style unavailable; session defaults apply.'); });
    return () => { ++revision.current; };
  }, [memoryEnabled]);
  function change(next: AssistantPreferences) {
    ++revision.current; setValue(next); setOverridden(true); setApproved(false);
    setNotice('Session style changed. Not saved to SQLite.');
  }
  async function save() {
    if (!memoryEnabled || !approved) return;
    setBusy(true);
    try { await memoryRequest('personality', 'PUT', { ...value, approved: true }); setApproved(false); setNotice('This exact assistant style was saved locally with your approval.'); }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : 'Style could not be saved.'); }
    finally { setBusy(false); }
  }
  return { value, overridden, approved, busy, notice, change, setApproved, save };
}

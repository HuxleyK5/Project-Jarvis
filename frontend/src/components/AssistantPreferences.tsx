import type { useAssistantPreferences, AssistantPreferences as Style } from '../hooks/useAssistantPreferences';

export default function AssistantPreferences({ preferences, memoryEnabled }: { preferences: ReturnType<typeof useAssistantPreferences>; memoryEnabled: boolean }) {
  return <details className="voice-controls assistant-preferences">
    <summary>ASSISTANT PREFERENCES</summary>
    <p>Adjust tone and answer detail for this session. Style never changes accuracy, uncertainty, privacy, or capability limits.</p>
    <div className="speech-settings">
      <label>Assistant tone<select aria-label="Assistant tone" value={preferences.value.tone} onChange={event => preferences.change({ ...preferences.value, tone: event.target.value as Style['tone'] })}><option value="professional">Professional</option><option value="friendly">Friendly</option><option value="formal">Formal</option></select></label>
      <label>Answer detail<select aria-label="Answer detail" value={preferences.value.detail} onChange={event => preferences.change({ ...preferences.value, detail: event.target.value as Style['detail'] })}><option value="balanced">Balanced</option><option value="concise">Concise</option><option value="detailed">Detailed</option></select></label>
    </div>
    <label><input type="checkbox" checked={preferences.approved} disabled={!memoryEnabled} onChange={event => preferences.setApproved(event.target.checked)} />I approve saving this exact tone/detail as my local assistant preferences.</label>
    <div className="voice-actions"><button type="button" disabled={!memoryEnabled || !preferences.approved || preferences.busy} onClick={() => void preferences.save()}>Save assistant preferences</button><button type="button" onClick={() => preferences.change({ tone: 'professional', detail: 'balanced' })}>Use session defaults</button></div>
    <p>{preferences.notice} {!memoryEnabled && 'Enable memory to approve persistent style settings.'}</p>
  </details>;
}

import type { VoiceState } from '../hooks/useVoice';

interface Props {
  state: VoiceState; error: string | null; transcript: string;
  consent: boolean; continuous: boolean; unavailable: boolean;
  setConsent: (value: boolean) => void; setContinuous: (value: boolean) => void;
  start: () => void; stop: () => void; finish: () => void;
}

export default function VoiceControls(props: Props) {
  const active = props.state !== 'idle';
  return <section className="voice-controls" id="voice" aria-labelledby="voice-title">
    <div className="voice-heading"><h2 id="voice-title">VOICE INPUT</h2><span className="micro-label" role="status">{props.state.toUpperCase()}</span></div>
    <p>Microphone audio is processed locally in memory. Recognized text is sent to JARVIS chat. No audio is saved or played back.</p>
    <label><input type="checkbox" checked={props.consent} onChange={event => props.setConsent(event.target.checked)} />I allow in-memory microphone capture, local transcription, and sending recognized text to chat for this session.</label>
    <label><input type="checkbox" checked={props.continuous} onChange={event => props.setContinuous(event.target.checked)} />Enable continuous “Hey JARVIS” wake listening</label>
    <div className="voice-actions"><button type="button" onClick={props.start} disabled={active || !props.consent || props.unavailable}>{props.continuous ? 'Start wake listening' : 'Record one command'}</button><button type="button" onClick={props.stop} disabled={!active}>Stop listening</button>{props.state === 'recording' && <button type="button" onClick={props.finish}>Finish and transcribe</button>}</div>
    {props.continuous && <p>Say “Hey JARVIS”, wait for RECORDING, then speak. Pretrained English detector; false activations and missed phrases are possible. Uncheck to disable continuous listening.</p>}
    {props.transcript && <p className="recognized-speech"><strong>Recognized speech:</strong> {props.transcript}</p>}
    {props.error && <p className="voice-error" role="alert">{props.error}</p>}
  </section>;
}

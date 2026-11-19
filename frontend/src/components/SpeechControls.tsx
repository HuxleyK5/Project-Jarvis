import type { useSpeech } from '../hooks/useSpeech';

export default function SpeechControls({ speech }: { speech: ReturnType<typeof useSpeech> }) {
  return <section className="voice-controls speech-controls" aria-labelledby="speech-title">
    <div className="voice-heading"><h2 id="speech-title">VOICE OUTPUT</h2><span className="micro-label" role="status">{speech.state.toUpperCase()}</span></div>
    <label><input type="checkbox" checked={speech.enabled} onChange={event => void speech.toggle(event.target.checked)} />Enable spoken responses (local Piper)</label>
    <p>Completed AI responses are spoken locally. New messages, microphone activation, and Stop interrupt playback. No generated audio files are saved.</p>
    <div className="speech-settings">
      <label>Audio output<select aria-label="Audio output device" value={speech.output} onChange={event => void speech.chooseOutput(event.target.value)}><option value="">System default output</option>{speech.devices.map(device => <option key={device.deviceId} value={device.deviceId}>{device.label || `Output ${device.deviceId.slice(0, 8)}`}</option>)}</select></label>
      <label>Volume<input aria-label="Speech volume" type="range" min="0" max="1" step="0.05" value={speech.volume} onChange={event => speech.setVolume(Number(event.target.value))} /></label>
      <label>Playback speed ({speech.speed.toFixed(1)}×)<input aria-label="Speech speed" type="range" min="0.5" max="2" step="0.1" value={speech.speed} onChange={event => speech.setSpeed(Number(event.target.value))} /></label>
    </div>
    <div className="voice-actions">
      <button type="button" onClick={() => void speech.requestOutput()}>Choose audio output</button>
      <button type="button" onClick={() => void speech.refreshDevices()}>Refresh outputs</button>
      <button type="button" onClick={() => void speech.pauseResume()} disabled={!['playing', 'paused'].includes(speech.state)}>{speech.state === 'paused' ? 'Resume speech' : 'Pause speech'}</button>
      <button type="button" onClick={speech.stop} disabled={!speech.active}>Stop speech</button>
      <button type="button" onClick={() => void speech.speak(speech.lastText)} disabled={!speech.enabled || !speech.lastText}>Replay last response</button>
    </div>
    {speech.error && <p className="voice-error speech-error" role="alert">{speech.error}</p>}
  </section>;
}

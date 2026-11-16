import { useEffect, useRef, useState } from 'react';

export type VoiceState = 'idle' | 'starting' | 'listening' | 'recording' | 'transcribing' | 'paused';

export function useVoice(onTranscript: (text: string) => Promise<void>) {
  const [state, setState] = useState<VoiceState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState('');
  const [level, setLevel] = useState(0);
  const liveState = useRef<VoiceState>('idle');
  const resources = useRef<{ stream?: MediaStream; context?: AudioContext; node?: AudioWorkletNode; source?: MediaStreamAudioSourceNode; socket?: WebSocket; gain?: GainNode }>({});
  const sequence = useRef(0);
  const callback = useRef(onTranscript);
  callback.current = onTranscript;

  function change(value: VoiceState) { liveState.current = value; setState(value); }
  function stop() {
    ++sequence.current;
    const value = resources.current;
    resources.current = {};
    value.node?.disconnect();
    value.source?.disconnect();
    value.gain?.disconnect();
    value.stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    if (value.socket && value.socket.readyState === WebSocket.OPEN) value.socket.send(JSON.stringify({ type: 'stop' }));
    value.socket?.close();
    void value.context?.close().catch(() => {});
    change('idle');
    setLevel(0);
  }

  useEffect(() => () => { stop(); }, []);

  async function start(consent: boolean, continuous: boolean) {
    if (liveState.current !== 'idle') return;
    if (!consent) { setError('Enable session microphone consent before listening.'); return; }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      setError('Microphone capture requires a supported browser on localhost (or HTTPS).'); return;
    }
    stop();
    const attempt = sequence.current;
    setError(null);
    change('starting');
    const current = () => attempt === sequence.current;
    try {
      const context = new AudioContext({ sampleRate: 16000 });
      resources.current.context = context;
      await context.resume();
      const response = await fetch('/api/voice/status', { signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error('Voice backend is unavailable. Restart the backend and check voice setup.');
      const status = await response.json();
      if (!current()) return;
      if (!(continuous ? status.wake_available : status.manual_available)) throw new Error(status.message || 'Voice models are missing. See docs/VOICE_SETUP.md.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false });
      if (!current()) { stream.getTracks().forEach(track => track.stop()); return; }
      resources.current.stream = stream;
      stream.getAudioTracks().forEach(track => { track.onended = () => { if (current()) { stop(); setError('Microphone disconnected or permission was revoked.'); } }; });
      await context.audioWorklet.addModule('/audio-capture.js');
      if (!current()) return;
      const node = new AudioWorkletNode(context, 'jarvis-capture');
      const source = context.createMediaStreamSource(stream);
      const gain = context.createGain();
      gain.gain.value = 0; // Keep the processing graph active without microphone playback.
      resources.current = { ...resources.current, node, source, gain };
      source.connect(node).connect(gain).connect(context.destination);
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/voice/listen`);
      resources.current.socket = socket;
      const readyTimer = window.setTimeout(() => { if (current() && liveState.current === 'starting') { stop(); setError('Voice model loading or connection timed out. Check local voice setup.'); } }, 30000);
      socket.onopen = () => { if (current()) socket.send(JSON.stringify({ consent: true, mode: continuous ? 'wake' : 'manual' })); };
      socket.onmessage = async event => {
        if (!current()) return;
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'state') {
            window.clearTimeout(readyTimer);
            if (!['recording', 'listening', 'transcribing', 'paused'].includes(message.state)) throw new Error('Invalid voice state');
            change(message.state);
          } else if (message.type === 'error') {
            stop(); setError(message.message || 'Voice processing failed.');
          } else if (message.type === 'transcript' || message.type === 'no_speech') {
            change('paused');
            if (message.type === 'transcript' && typeof message.text === 'string' && message.text.trim()) {
              setTranscript(message.text);
              // Manual mode releases the microphone as soon as recognition completes.
              if (!continuous) stop();
              await callback.current(message.text);
            } else setError(message.message || 'No clear speech recognized.');
            if (continuous && current() && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'resume' }));
          }
        } catch {
          if (current()) { stop(); setError('The voice session could not be completed.'); }
        }
      };
      socket.onerror = () => { if (current()) { stop(); setError('Voice connection failed. Check that the local backend supports WebSockets.'); } };
      socket.onclose = () => {
        window.clearTimeout(readyTimer);
        if (current()) { const unexpected = liveState.current !== 'paused'; stop(); if (unexpected) setError('Voice connection closed. Start listening again.'); }
      };
      node.port.onmessage = event => {
        if (!current()) return;
        setLevel(event.data.level);
        if (socket.readyState === WebSocket.OPEN && ['listening', 'recording'].includes(liveState.current)) {
          if (socket.bufferedAmount > 2560 * 15) { stop(); setError('Audio processing is falling behind. Try manual mode or close other voice sessions.'); return; }
          socket.send(event.data.pcm);
        }
      };
    } catch (reason) {
      if (!current()) return;
      stop();
      const name = reason instanceof DOMException ? reason.name : '';
      setError(name === 'NotAllowedError' ? 'Microphone permission denied. Allow microphone access for this localhost page and try again.'
        : name === 'NotFoundError' ? 'No microphone was found. Connect or select a microphone and try again.'
        : name === 'NotReadableError' ? 'The microphone is unavailable or in use by another application.'
        : reason instanceof Error ? reason.message : 'Could not start microphone capture.');
    }
  }

  function finish() {
    if (liveState.current === 'recording') {
      change('transcribing');
      resources.current.socket?.send(JSON.stringify({ type: 'finish' }));
    }
  }
  return { state, error, transcript, level, start, stop, finish, active: state !== 'idle' };
}

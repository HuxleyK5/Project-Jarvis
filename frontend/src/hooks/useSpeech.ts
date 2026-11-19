import { useEffect, useRef, useState } from 'react';

type OutputContext = AudioContext & { setSinkId?: (id: string) => Promise<void> };
type OutputDevices = MediaDevices & { selectAudioOutput?: () => Promise<MediaDeviceInfo> };
export type SpeechState = 'idle' | 'generating' | 'playing' | 'paused';

export function useSpeech() {
  const [enabled, setEnabled] = useState(false);
  const [state, setState] = useState<SpeechState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [speed, setSpeed] = useState(1);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [output, setOutput] = useState('');
  const [lastText, setLastText] = useState('');
  const context = useRef<OutputContext | null>(null);
  const gain = useRef<GainNode | null>(null);
  const analyser = useRef<AnalyserNode | null>(null);
  const source = useRef<AudioBufferSourceNode | null>(null);
  const abort = useRef<AbortController | null>(null);
  const complete = useRef<(() => void) | null>(null);
  const animation = useRef(0);
  const sequence = useRef(0);
  const enabledRef = useRef(false);
  const speedRef = useRef(speed);

  function stop() {
    ++sequence.current;
    abort.current?.abort(); abort.current = null;
    if (source.current) {
      source.current.onended = null;
      try { source.current.stop(); } catch { /* Already ended. */ }
      source.current.disconnect(); source.current = null;
    }
    complete.current?.(); complete.current = null;
    cancelAnimationFrame(animation.current);
    setLevel(0); setState('idle');
  }

  function ensureContext() {
    if (!context.current) {
      context.current = new AudioContext();
      gain.current = context.current.createGain();
      gain.current.gain.value = volume;
      analyser.current = context.current.createAnalyser();
      analyser.current.fftSize = 256;
      gain.current.connect(analyser.current).connect(context.current.destination);
    }
    return context.current;
  }

  useEffect(() => () => { stop(); void context.current?.close(); }, []);

  async function toggle(value: boolean) {
    enabledRef.current = value; setEnabled(value);
    if (!value) { stop(); return; }
    setError(null);
    try {
      // Resume from the explicit user gesture, rather than from a delayed AI callback.
      await ensureContext().resume();
      const response = await fetch('/api/speech/status', { signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error('Speech output backend is unavailable.');
      const status = await response.json();
      if (!status.available) throw new Error(status.message || 'Piper voice is missing.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Cannot initialize local speech output.'); }
  }

  async function refreshDevices() {
    try {
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'audiooutput' && device.deviceId && device.deviceId !== 'default'));
    } catch { setError('Audio output devices could not be listed. Check browser device permissions.'); }
  }

  async function chooseOutput(id: string) {
    try {
      const ctx = ensureContext();
      if (!ctx.setSinkId && id) throw new Error('This browser cannot select an audio output. Use its default output or a supported Chromium browser.');
      if (ctx.setSinkId) await ctx.setSinkId(id);
      setOutput(id); setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Selected output is unavailable.'); }
  }

  async function requestOutput() {
    try {
      const media = navigator.mediaDevices as OutputDevices;
      if (media.selectAudioOutput) {
        const selected = await media.selectAudioOutput();
        await refreshDevices();
        setDevices(value => value.some(item => item.deviceId === selected.deviceId) ? value : [...value, selected]);
        await chooseOutput(selected.deviceId);
      } else {
        await refreshDevices();
        setError('Use the available device list. If labels/devices are hidden, grant output access in a supported browser or select the system default output.');
      }
    } catch { setError('Audio output selection was cancelled or denied. The previous output remains selected.'); }
  }

  async function speak(text: string) {
    setLastText(text);
    if (!enabledRef.current || !text.trim()) return;
    stop(); setError(null);
    const attempt = sequence.current;
    const current = () => attempt === sequence.current && enabledRef.current;
    const controller = new AbortController(); abort.current = controller;
    let timedOut = false;
    // Limit each native synthesis job while retaining the complete response in order.
    const chunks = text.match(/[\s\S]{1,900}(?:\s|$)|[\s\S]{1,900}/g) ?? [];
    try {
      const ctx = ensureContext();
      await ctx.resume();
      for (const chunk of chunks) {
        if (!current()) return;
        setState('generating');
        const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, 65000);
        let data: ArrayBuffer;
        try {
          const response = await fetch('/api/speech/synthesize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: chunk }), signal: controller.signal });
          if (!response.ok) {
            const body = await response.json().catch(() => null);
            throw new Error(body?.error?.message || `Speech generation failed (HTTP ${response.status}).`);
          }
          if (!response.headers.get('content-type')?.includes('audio/wav')) throw new Error('The speech backend returned an invalid audio format.');
          data = await response.arrayBuffer();
        } finally { window.clearTimeout(timer); }
        if (!current()) return;
        const buffer = await ctx.decodeAudioData(data);
        if (!current()) return;
        const node = ctx.createBufferSource(); source.current = node;
        node.buffer = buffer; node.playbackRate.value = speedRef.current;
        node.connect(gain.current!);
        const samples = new Uint8Array(analyser.current!.fftSize);
        const meter = () => {
          if (!current() || ctx.state !== 'running') return;
          analyser.current!.getByteTimeDomainData(samples);
          setLevel(Math.sqrt(samples.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / samples.length));
          animation.current = requestAnimationFrame(meter);
        };
        setState('playing'); meter();
        await new Promise<void>(resolve => {
          complete.current = resolve;
          node.onended = () => { node.disconnect(); source.current = null; complete.current = null; cancelAnimationFrame(animation.current); setLevel(0); resolve(); };
          node.start();
        });
      }
      if (current()) { abort.current = null; setState('idle'); }
    } catch (reason) {
      if (!current()) return;
      stop();
      setError(timedOut ? 'Speech generation timed out. Try a shorter response.' : reason instanceof Error ? reason.message : 'Local speech playback failed.');
    }
  }

  async function pauseResume() {
    try {
      if (!context.current || !source.current) return;
      if (context.current.state === 'running') {
        await context.current.suspend(); cancelAnimationFrame(animation.current); setLevel(0); setState('paused');
      } else {
        await context.current.resume(); setState('playing');
        const samples = new Uint8Array(analyser.current!.fftSize);
        const meter = () => {
          if (!source.current || context.current?.state !== 'running') return;
          analyser.current!.getByteTimeDomainData(samples);
          setLevel(Math.sqrt(samples.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / samples.length));
          animation.current = requestAnimationFrame(meter);
        };
        meter();
      }
    } catch { setError('Audio playback could not be paused/resumed. Stop playback and try again.'); }
  }

  return { enabled, state, error, level, volume, speed, devices, output, lastText, active: state !== 'idle',
    toggle, speak, stop, pauseResume, refreshDevices, chooseOutput, requestOutput,
    setVolume: (value: number) => { setVolume(value); if (gain.current) gain.current.gain.value = value; },
    setSpeed: (value: number) => { setSpeed(value); speedRef.current = value; if (source.current) source.current.playbackRate.value = value; } };
}

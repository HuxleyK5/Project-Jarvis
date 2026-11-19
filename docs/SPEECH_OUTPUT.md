# JARVIS local speech output

## Implemented, with local setup still missing

Piper speech generation and browser playback are implemented. The user explicitly chose **no Piper installation and no voice download** for this increment. The earlier decision not to install/download OpenWakeWord and Whisper remains unchanged. Real Piper synthesis, audible output through physical devices, and real full-voice conversation therefore remain unverified. Existing typed chat continues to work when speech setup is missing.

Nothing is installed or downloaded automatically. No system audio setting is modified and no real microphone is opened by the tests. Browser tests use generated test tones, intercepted model responses, and a muted Chromium process. Those tests validate the complete application flow, not actual model quality or speaker hardware.

## User controls

Start the backend and frontend as described in the README, then open http://127.0.0.1:5173. Restart an older running backend to load the new speech routes.

- **Enable spoken responses (local Piper)**: off by default on every page load. Enabling checks local setup and prepares browser audio through a user gesture. Disabling cancels generation/playback immediately in the browser.
- **Audio output**: defaults to the system's default output. Refresh lists browser-visible output devices. Choose audio output opens the browser's output picker where supported; otherwise it refreshes the available list and explains the limitation. A non-default selection requires `AudioContext.setSinkId`; if unavailable or denied, the previous output remains selected and an error is shown. JARVIS does not secretly switch back to another device.
- **Volume**: 0–100% through a Web Audio gain node.
- **Playback speed**: 0.5–2× through Web Audio playback rate; this also affects pitch. Piper's independent length-scale setting is available for voice timing adjustments.
- **Pause / Resume**: pauses or resumes the current utterance's audio context.
- **Stop speech**: interrupts playback and cancels pending HTTP synthesis, preventing a late result from starting.
- **Replay last response**: regenerates the latest response's audio locally; it does not ask the AI for another answer. The last response text is session-only; synthesized audio is not cached to disk.

Some browsers block delayed autoplay, hide device labels, or lack output routing support. Use a supported current browser on localhost and an explicit enable/replay gesture. Physical output availability, volume/mute settings, and audibility must be verified manually. The app does not change OS permissions or default devices.

## Response and wake flow

Only completed AI replies are spoken. Failed/stopped partial generations remain on screen without being read as successful answers. Text continues to stream visibly; speech starts after completion and is broken into bounded chunks which play sequentially. There is one current browser source, with no queue of overlapping answers. New typed input or microphone activation interrupts the old audio. Replies may still contain model errors; synthesis is not factual verification.

In continuous wake mode, a detected wake phrase adds the explicit acknowledgement **“Yes, how can I help?”** to the conversation. This is labeled **Wake acknowledgement**, not presented as a generated AI answer, and is excluded from AI context. If speech is enabled and configured, Piper reads it before command capture resumes. The recognized question then uses the existing chat context, and the completed answer is both displayed and spoken. Wake listening resumes after playback (or after Stop/error).

The microphone's audio forwarding is blocked while speech is generating, playing, or paused. This prevents the application from intentionally sending its own speech back to recognition. The microphone track can remain open in consented continuous mode, but frames are discarded rather than queued. The voice socket sends periodic control heartbeats, without audio, so a long synthesis/playback pause does not end listening prematurely. Acoustic echo cancellation is still browser/device-dependent; a headset can help. This is half-duplex behavior: interruption uses the visible Stop/microphone controls, not wake-word detection during playback.

The central waveform uses Web Audio analyser samples from the real playback graph while speech is active, rather than decorative random bars. During capture it uses measured microphone level. Paused/stopped playback resets the output meter. Speaker-level audibility is not inferred from the analyser.

## Local-only synthesis and configuration

`backend/voice/tts.py` lazily loads Piper on CPU using an explicit local ONNX path and adjacent JSON configuration. It uses the [official Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md). WAV output is generated into an in-memory buffer; the endpoint returns it with `Cache-Control: no-store`. No Piper HTTP server, remote speech provider, browser SpeechSynthesis fallback, or model downloader is used.

Default files (not present/downloaded):

```text
data/models/voice/piper/en_US-lessac-medium.onnx
data/models/voice/piper/en_US-lessac-medium.onnx.json
```

This directory is already excluded from Git by the project's `data/` rule. The default Lessac medium model is an English US, single-speaker model with native 22050 Hz output; see its [official model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD). It is a standard pretrained voice, not an imitation of a film actor. Review the engine's [licensing guidance](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/LICENSING.md) and each voice's model-card/dataset terms before redistribution. Do not assume all voices share identical licensing.

Process environment settings, documented in `.env.example` (not auto-loaded):

| Setting | Default | Meaning |
| --- | --- | --- |
| JARVIS_PIPER_MODEL | repo/data/models/voice/piper/en_US-lessac-medium.onnx | Explicit local ONNX path; configuration must be at the same path plus .json |
| JARVIS_PIPER_LENGTH_SCALE | 1 | 0.5–2; greater values slow synthesis timing |
| JARVIS_PIPER_NOISE_SCALE | 0.667 | 0–2; synthesis variation |
| JARVIS_PIPER_NOISE_W_SCALE | 0.8 | 0–2; phoneme-width variation |
| JARVIS_PIPER_SPEAKER | 0 | Nonnegative speaker index; must exist in the selected voice |

Restart the backend after changing settings. Choose another compatible Piper voice by changing the local model path and supplying its matching config. No ONNX/GPU/CUDA settings are altered. CPU inference avoids competing with Ollama for the inspected 6 GiB VRAM; native runtime compatibility and latency on the older Windows installation are not yet verified.

For a future **separately approved** setup, the optional installation command would be:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/voice/tts-requirements.txt
```

That command was not run. After separate model-download approval, obtain the `.onnx` and `.onnx.json` files from the [official voice repository](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium) and place them as above. Installation/download and actual voice-input prerequisites remain outside this increment's authorized actions.

## API and resource handling

`GET /speech/status` checks Piper metadata and the two files without loading the model. `available: true` is a setup-presence check, not proof of successful synthesis.

`POST /speech/synthesize` accepts `{"text":"Hello"}` with 1–1000 nonblank characters and no model/path overrides. It returns `audio/wav`; missing setup returns 503, a busy native worker 429, native failure 502, and a 60-second synthesis deadline 504. The browser chunks long responses, decodes each WAV, and waits for playback before requesting the next one.

One dedicated worker serializes native synthesis. Cancelling HTTP or Stop cannot forcibly terminate an ONNX call already running; its result is discarded by the stopped browser. The service rejects overlapping native jobs until that worker actually finishes. Browser generation IDs suppress stale playback, AbortController cancels requests, and stopping disconnects the current source and resolves its waiter. A 65-second browser fetch limit covers the backend synthesis deadline. These protections operate per browser dashboard; separate browser tabs or unrelated applications can still play audio independently.

## Verification and real acceptance test

From the project root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm test
```

The synthetic end-to-end test covers wake activation → spoken acknowledgement → recognized question → streamed/displayed AI answer → synthesized response → return to wake listening. Additional tests cover missing assets, device-routing calls, pause/resume, stop during pending synthesis, replay, disabled output, waveform measurements, and native-job overlap prevention. Test audio is muted and does not access physical microphones/speakers as an acceptance test.

After separately approved prerequisites exist, enable voice output, select the intended output, and first verify a typed reply is audible. Then opt into voice input and continuous wake mode, say “Hey JARVIS”, wait for the acknowledgement and RECORDING indicator, ask “What can you help me with?”, and verify both the visible text and audible answer. Finally verify Stop, output disable, and correct device routing. None of those real-model/hardware acceptance results are claimed for the current missing-model environment.

Verification for this increment: 45 backend tests and 20 Chromium tests passed, including the synthetic full-conversation test; the production TypeScript/Vite build passed. Targeted voice/speech tests were rerun after the heartbeat change and passed. No dependencies or models were installed/downloaded. The pre-existing non-failing Starlette HTTPX deprecation warning remains.

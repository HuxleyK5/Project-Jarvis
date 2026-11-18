# Phase 2: local voice input

## Current status and permission

The user explicitly chose **no dependency installation** and **no voice model downloads** for this increment. The code is implemented, but actual wake-word recognition and Faster-Whisper inference are not enabled or verified on this computer. The backend remains usable for typed chat without voice extras. Missing dependencies/models produce an actionable setup message, never a fabricated transcript.

Tests use injected models and synthetic audio, not physical microphones or personal recordings. No microphone was opened, no audio was saved, no model was downloaded, and no system settings were changed during implementation. Previous device inspection found virtual NDI inputs; a working physical microphone remains unverified.

## Audio flow

1. Voice consent and continuous listening both start unchecked on every page load.
2. The user checks session consent, then clicks **Record one command** or enables continuous mode and clicks **Start wake listening**. The microphone icon uses the same controls and cannot bypass consent.
3. The dashboard first checks local assets, then requests browser microphone permission. Audio is captured by `getUserMedia`, mixed/resampled by an AudioWorklet to mono PCM16 at 16kHz, and sent to the local FastAPI WebSocket in 80ms frames. The audio graph is muted; microphone monitoring is not played through speakers.
4. Manual mode bypasses wake detection. Wake mode processes audio with the pretrained **Hey JARVIS** detector. After activation, wait for RECORDING before speaking; the wake phrase itself is not included in the utterance buffer.
5. A bounded utterance ends after approximately 960ms of quiet following speech, after 12 seconds, or when the user clicks **Finish and transcribe**. Five seconds without speech ends capture without running transcription. RMS gating and a short minimum speech duration suppress silence and isolated clicks; they are not a full speech/noise classifier.
6. Faster-Whisper runs locally on CPU with INT8 using an explicit local model directory and `local_files_only=True`. Recognized text appears under voice controls and as a **YOU · VOICE** chat message when submitted. It uses the existing `/chat` streaming endpoint and the same conversation context as typed messages. If chat is busy or disconnected, recognized text is placed in the input instead.
7. Manual mode releases microphone tracks as soon as recognition completes. Continuous mode pauses audio forwarding during transcription/chat and resumes wake listening after chat finishes. The browser microphone remains active during that pause until Stop; paused audio is not queued for future recognition.

**Stop listening**, unchecking consent, changing continuous mode, or leaving the page closes the socket and releases microphone tracks. Stop discards the unfinished utterance; it does not trigger transcription. A native inference call already executing cannot be forcibly interrupted safely; its bounded in-memory work may finish, but a stopped browser session ignores its result. Stopping listening does not stop an AI response already submitted; use the separate chat Stop control for that.

Audio is never intentionally written to disk or transcript logs. Short PCM/feature buffers exist in memory only during opted-in listening. The currently recognized text and chat history are browser-session data, cleared on reload. This is application-level memory retention, not a promise about operating-system swap, browser internals, or external device drivers. Do not record or save conversation fixtures without separate explicit recording permission.

## Required assets (not downloaded)

Default directory, already covered by the repository's ignored `data/` rule:

```text
data/models/voice/
  wake/
    hey_jarvis_v0.1.onnx
    melspectrogram.onnx
    embedding_model.onnx
  whisper-tiny.en/
    model.bin
    config.json
    tokenizer.json
    vocabulary.json
```

After **new explicit approval** for installation, the optional Windows dependency command would be:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/voice/requirements.txt
```

This command was not run. The optional dependency set and native Windows binaries remain installation-unverified. Do not install full training extras or CUDA packages. `websockets` supplies Uvicorn's optional WebSocket transport; the base HTTP API does not need it. Python audio libraries are used in the model adapters; browser capture avoids a second process opening the microphone without browser permissions.

After **separate new explicit model-download approval**, obtain only the named ONNX assets from the [official OpenWakeWord v0.5.1 release](https://github.com/dscripka/openWakeWord/releases/tag/v0.5.1) and the converted `tiny.en` model files from [Systran/faster-whisper-tiny.en](https://huggingface.co/Systran/faster-whisper-tiny.en/tree/main), placing them as shown above. Do not invoke a broad downloader or pass a model name that could fetch weights implicitly. Models are loaded only after a consented listening request. The status endpoint only inspects dependency metadata and file presence, which does not prove native runtime compatibility or model integrity.

CPU INT8 `tiny.en` is chosen for the inspected i7/16 GiB system and avoids competing with Ollama for the GTX 1060's limited VRAM or requiring CUDA/driver changes. Faster-Whisper supports local CPU INT8 execution and model directories; see its [official usage guidance](https://github.com/SYSTRAN/faster-whisper#usage). Actual latency and accuracy on this machine are unknown.

## Pretrained wake model limitations

The supported phrase is **Hey JARVIS**, using the existing pretrained model, not a custom-trained asset. Changing the displayed phrase alone cannot teach a model a different wake phrase; unsupported phrases are rejected. The [OpenWakeWord documentation](https://github.com/dscripka/openWakeWord/tree/v0.6.0#readme) describes English models, 16kHz PCM input, and tunable confidence thresholds. Accents, distance, background speech, and noise can cause missed or false activations. This detector is not speaker authentication. Speak after activation rather than running the wake phrase and command together without a pause.

OpenWakeWord code is Apache 2.0, but its included pretrained wake models have **CC BY-NC-SA 4.0** terms, including noncommercial limitations; see the [upstream license section](https://github.com/dscripka/openWakeWord/tree/v0.6.0#license). Do not assume the pretrained weights have the same license as the code. No paid API is required.

The initial transcription model is English-only `tiny.en`; it may misrecognize speech or hallucinate words in noise. Silence gating and output probability filters reduce, but do not eliminate, that risk. Recognized text may be sent automatically once the user has consented; review visible text and stop continuous mode when it is not wanted.

## Configuration and run

Process environment variables (the `.env.example` file is not automatically loaded):

| Setting | Default | Purpose |
| --- | --- | --- |
| JARVIS_WAKE_PHRASE | Hey JARVIS | Must match the included pretrained model |
| JARVIS_WAKE_THRESHOLD | 0.5 | Allowed 0.1–0.99; tune only with actual wake tests |
| JARVIS_VOICE_MODELS | repo/data/models/voice | Optional absolute local asset directory |

Restart the backend after changing these settings. Normal startup remains:

```powershell
.\.venv\Scripts\python.exe -m backend.main
```

In another terminal:

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. `GET http://127.0.0.1:8000/voice/status` reports setup readiness without microphone access. The Vite development and preview proxies forward local WebSocket traffic. Use a current browser with AudioWorklet and microphone support on localhost. Browser permissions, Windows microphone privacy settings, device selection, or an occupied/disconnected input can prevent capture. No settings are changed automatically. Use the browser/OS device selector to choose an actual input if a virtual NDI endpoint is the default.

Only the local dashboard origins on ports 5173, 4173, or the configured backend port can open the voice socket. Origin filtering is not authentication against other software on the computer. The implementation targets local HTTP; remote hosting/HTTPS configuration and background startup services are outside Phase 2.

## Tests and separate acceptance checks

Run current deterministic tests without voice dependencies or models:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p "test_voice_wake.py" -v
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p "test_voice_speech.py" -v
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm test
```

Wake tests cover thresholding and the rule that background audio never enters transcription. Speech tests separately cover manual capture, silence/click suppression, bounds, cleanup, and the local-only Whisper loader contract. ASGI tests cover consent, origins, finish/stop/resume, and cleanup. Browser tests use a silent-to-speakers synthetic oscillator and intercepted voice events to check real AudioWorklet PCM framing, permission errors, automatic chat submission, consent withdrawal, and microphone-track release. They do not assess model accuracy and do not touch a physical microphone.

Once installation and model downloads are separately approved and complete, test actual engines independently on existing authorized or synthetic mono PCM16 16kHz WAV fixtures, at most 12 seconds long:

```powershell
.\.venv\Scripts\python.exe -m backend.voice.diagnostics wake path\to\hey-jarvis-fixture.wav
.\.venv\Scripts\python.exe -m backend.voice.diagnostics speech path\to\command-fixture.wav
```

Diagnostics only read supplied files, never open a microphone, never download models, and never write audio. Then perform opt-in dashboard acceptance checks: manual recognition first, wake activation second, follow-up chat third, and Stop/permission revocation last. No spoken responses are implemented.

# Local AI setup and verification

## Status on November 16, 2026

The Ollama executable was not found in PATH or the standard per-user/Program Files locations checked. The local service at `http://127.0.0.1:11434/api/tags` was unreachable. Installed models therefore could not be enumerated, and actual model inference could not be tested. No Ollama installation, model download, driver change, or system setting change was performed.

The machine still reports Windows 10 Pro build 19041 and NVIDIA driver 536.99. Current [Ollama Windows requirements](https://docs.ollama.com/windows) specify Windows 10 22H2 or newer and NVIDIA drivers 551.61 or newer. The [hardware support page](https://docs.ollama.com/gpu) lists the GTX 1060 as compute capability 6.1 and requires driver 570 or newer for that capability range. This machine is below those current prerequisites. Review compatibility before installation; any Windows/driver changes require separate explicit approval. No particular upgrade path has been applied or verified.

## Default model

Based on [HARDWARE_REPORT.md](HARDWARE_REPORT.md), JARVIS defaults to `qwen3:4b`, a roughly 2.5 GB Q4_K_M model according to the [official model listing](https://ollama.com/library/qwen3:4b). With about 16 GiB RAM and 6 GiB VRAM, this follows the report's preferred 3B–4B quantized range. Actual speed and GPU support are unverified. Download size is not runtime memory usage. `qwen3:1.7b` is a smaller alternative if separately approved and installed; changing the configuration does not install it.

Default options: 4096 context tokens, 512 output tokens, no separate thinking output, and one backend generation at a time. Output limits and finite context can truncate answers or omit older turns. The system prompt encourages honest uncertainty; it cannot guarantee that a model never makes mistakes.

## Setup steps requiring approval

1. Resolve the compatibility questions above with the user before changing Windows, drivers, or software.
2. After explicit installation approval, obtain Ollama from its [official Windows download](https://ollama.com/download/windows). Keep its API bound to loopback. Do not enable remote exposure.
3. Start the Ollama application. If using the CLI instead, run `ollama serve` in a terminal; do not start a second server if the application is already serving port 11434.
4. List installed models without downloading anything:

   ```powershell
   ollama list
   Invoke-RestMethod http://127.0.0.1:11434/api/tags
   ```

5. **Only after separate explicit approval for this model download**, run:

   ```powershell
   ollama pull qwen3:4b
   ```

   This is a download command, not a prerequisite check. JARVIS does not call `/api/pull`, run the Ollama CLI, or install anything. Model storage remains unchanged; choosing D: storage would be a separate approved configuration task.

## Configure and run JARVIS

In PowerShell at the repository root:

```powershell
$env:JARVIS_MODEL_PROVIDER = "ollama"
$env:JARVIS_OLLAMA_URL = "http://127.0.0.1:11434"
$env:JARVIS_MODEL = "qwen3:4b"
.\.venv\Scripts\python.exe -m backend.main
```

Defaults already match these values. The root `.env.example` is a reference only; it is not automatically loaded. Restart the backend after changing the model or provider settings. Only Ollama is currently implemented; another provider requires an adapter implementing `backend/core/providers.py`, registration in `backend/integrations/provider_factory.py`, and configuration validation changes. Changing between already installed Ollama models requires only `JARVIS_MODEL` and a restart. Known cloud tags and entries advertising remote model metadata are rejected.

Additional process settings:

| Variable | Default | Accepted range / purpose |
| --- | --- | --- |
| JARVIS_CONTEXT_WINDOW | 4096 | 2048–8192 tokens; larger contexts consume more memory |
| JARVIS_MAX_OUTPUT_TOKENS | 512 | 64–2048; must be below context window |
| JARVIS_GENERATION_TIMEOUT | 120 | 10–600 seconds total generation deadline |

The frontend has an independent 180-second overall response timeout. If a larger backend deadline is needed later, update the frontend timeout in `useChat.ts` as well. Individual stalled Ollama stream reads time out after 30 seconds. Health discovery has a 2-second timeout and does not load the model.

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173 while both servers run. Health at http://127.0.0.1:8000/health reports whether Ollama is reachable and the configured model is installed. `ai_connected: true` means available for a request, not warmed up or successfully benchmarked. Send a greeting, then try “My preferred name is Alex” followed by “What name did I give you?” to verify a real follow-up. Use Stop to cancel generation. Reloading the page starts a new conversation.

## Troubleshooting

| Status or symptom | Action |
| --- | --- |
| ollama_unavailable / ollama_timeout | Start/check the local Ollama service and configured URL. Backend liveness remains independent. |
| model_missing | Select a model from `ollama list`, or request approval before downloading the selected model. |
| remote_model | Select an installed local model rather than an entry pointing to a cloud service. |
| model_busy | Wait for the other local request to finish or stop it. |
| generation_timeout / output_limit | Ask a narrower question; consider a smaller installed model or appropriate configuration limits. Partial answers are labeled incomplete. |
| ollama_error / empty_response | Inspect Ollama logs, model/runtime compatibility, and available memory. JARVIS does not return raw provider errors or pretend a reply succeeded. |

## Tests and limits

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm test
```

Backend tests use injected providers and HTTPX MockTransport. Browser chat tests use test-only intercepted streams, while the health/unavailable-provider test contacts the real FastAPI application. These verify integration behavior, not model intelligence. No canned answers are part of production code. Natural-language quality, actual model loading, speed, GPU acceleration, and live inference remain unverified until a compatible Ollama service and model are available.

Verification completed for this increment: 23 backend tests passed, 10 Chromium browser tests passed, the TypeScript/production build passed, and Python dependency consistency checks passed. The pre-existing non-failing Starlette HTTPX deprecation warning remains. No additional dependencies were installed in this increment.

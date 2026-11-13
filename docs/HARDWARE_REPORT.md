# JARVIS Phase 0: Hardware and Development Environment

Inspection date: November 13, 2026 (America/Phoenix).

## Scope and method

Read-only inspection used PowerShell CIM queries, Plug and Play enumeration, Windows audio endpoint and installation registry reads, executable discovery, version commands, and NVIDIA's `nvidia-smi`. No software was installed, models downloaded, or settings changed. This report is the only project addition. The project initially contained only `.git`; no application, documentation, or project instruction files were found.

## Hardware

| Item | Detected finding |
| --- | --- |
| Windows | Windows 10 Pro, 64-bit, release 2004; version 10.0.19041; registry build revision 19041.572 |
| CPU | Intel Core i7-8700K @ 3.70 GHz; 6 cores, 12 logical processors |
| GPU | NVIDIA GeForce GTX 1060 6GB |
| GPU memory | 6144 MiB (6 GiB) dedicated VRAM, confirmed by `nvidia-smi` |
| NVIDIA driver | 536.99 (`nvidia-smi`); Windows driver version 31.0.15.3699 |
| Total physical RAM | 17,100,517,376 bytes, approximately 15.93 GiB (16 GB class) |

`Win32_VideoController.AdapterRAM` reported 4,293,918,720 bytes, inconsistent with the GPU's name and NVIDIA's direct query. The report uses the NVIDIA value rather than that unreliable field.

### Available storage

| Local drive | Total capacity | Free space at inspection |
| --- | ---: | ---: |
| C: (project location) | 231.89 GiB | 30.40 GiB |
| D: | 1,863.01 GiB | 1,766.19 GiB |

GiB means 1,073,741,824 bytes. Drive media type (SSD/HDD) was not determined: unknown. Space values are a snapshot.

## Development tools

| Tool | Status and version | Executable location |
| --- | --- | --- |
| Python | Installed; Python 3.12.4; Python launcher also detects 3.12 | `C:\Users\tvhsstudent\AppData\Local\Programs\Python\Python312\python.exe` |
| Node.js | Installed; v20.16.0; npm command present, npm version not inspected | `C:\Program Files\nodejs\node.exe` |
| Git | Installed; 2.47.1.windows.1 | `C:\Users\tvhsstudent\AppData\Local\Programs\Git\cmd\git.exe` |
| Ollama | Not detected; installation status unknown outside checked locations | No PATH command, matching standard uninstall registration, running `ollama` process, or executable at the checked per-user and Program Files locations |

Ollama paths checked: `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` and `%ProgramFiles%\Ollama\ollama.exe`. No whole-disk search was performed. A portable or custom installation cannot be ruled out.

## Microphone and audio playback

Windows reports NVIDIA High Definition Audio, High Definition Audio Device (Microsoft), and NDI Webcam Audio (NewTek) sound devices with status OK.

| Capability | Findings | Practical availability |
| --- | --- | --- |
| Microphone/input | Four NDI virtual capture endpoints, Webcam 1 through Webcam 4, are present, status OK, and active (endpoint state 1). Both physical entries named Microphone and the Line In entry report unplugged (state 8). | Virtual inputs detected. A usable physical microphone, live NDI source, recording permissions, and actual signal capture are unknown. |
| Speaker/playback | Headphones, Digital Audio (S/PDIF), and Acer KG240 playback endpoints are present, status OK, and active (state 1). The entry named Speakers reports unplugged (state 8). | Windows playback endpoints are available. Audible output, attached speakers/headphones, volume, and default routing are unknown. |

No microphone recording or playback test was performed. Device enumeration does not prove that sound can be captured or heard. Old/nonpresent audio entries were not treated as available devices.

## Local AI model sizing recommendations

These are hardware-based estimates, not benchmark results. No inference runtime or model was installed or tested. Runtime compatibility with this Windows build, GPU, and driver remains unverified.

| Model size | Recommendation for this computer |
| --- | --- |
| 1B–2B parameters, roughly 4-bit quantized | Good starting range for low memory use and initial local experiments. Example: Qwen3 1.7B, listed at approximately 1.4 GB download size. |
| 3B–4B, roughly 4-bit quantized | Preferred starting range for JARVIS experiments, balancing capability and memory headroom. Example: Qwen3 4B, approximately 2.5 GB download size. Start with a modest context such as 2K–4K tokens and one loaded model. |
| 7B–8B, roughly 4-bit quantized | Possible experimental range, but tight for 6 GiB VRAM once runtime and context memory are included. Qwen3 8B is approximately 5.2 GB on disk; partial CPU offload or shorter context may be needed and could reduce speed. |
| 14B and larger | Not recommended as the initial target with 16 GB system RAM and 6 GiB VRAM. Qwen3 14B alone is approximately 9.3 GB on disk, leaving limited system headroom and requiring substantial CPU involvement. Larger models are increasingly impractical here. |

Model download size is not total runtime memory. Context cache, runtime buffers, Windows, display usage, and future speech components also consume memory. No tokens-per-second estimate is claimed. Prefer the roomy D: drive for future model storage, subject to approval before installation or downloads. These examples do not require a paid API.

Example sizes were checked against the official [Ollama Qwen3 model library](https://ollama.com/library/qwen3). Hardware suitability is an inference from detected RAM/VRAM, not a guarantee from the model listing. Choose the exact model, license, runtime, and quantization in a later authorized phase.

## Verification and follow-up

Python, Node.js, and Git version commands succeeded. NVIDIA's hardware query succeeded. Audio findings were checked against both PnP status and registry endpoint states. The project had a clean Git status before this report was added.

There is no JARVIS application to run or test in Phase 0. To repeat basic read-only checks in PowerShell, run `python --version`, `node --version`, `git --version`, and `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader`. Actual microphone capture, audible playback, and local AI performance require separate testing in a later authorized task.

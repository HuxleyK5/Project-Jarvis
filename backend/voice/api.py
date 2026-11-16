"""Consent-gated local microphone stream; never opens a server-side microphone."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.voice.config import VoiceSettings
from backend.voice.engines import FasterWhisperRecognizer, OpenWakeWordDetector, VoiceError, availability
from backend.voice.session import VoiceSession


class VoiceService:
    def __init__(self, settings: VoiceSettings):
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-voice")
        self.lock = asyncio.Lock()
        self.recognizer = None

    def create_session(self, mode):
        if self.recognizer is None:
            self.recognizer = FasterWhisperRecognizer(self.settings)
        detector = OpenWakeWordDetector(self.settings) if mode == "wake" else None
        return VoiceSession(mode, self.settings, self.recognizer, detector)

    async def run(self, function, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, function, *args)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)


router = APIRouter(prefix="/voice", tags=["Voice"])


@router.get("/status")
async def voice_status():
    return availability(VoiceSettings.from_env())


@router.websocket("/listen")
async def listen(socket: WebSocket):
    origin = urlsplit(socket.headers.get("origin", ""))
    if origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"} or origin.port not in {5173, 4173, socket.app.state.settings.port}:
        await socket.close(code=1008, reason="Only the local dashboard may open voice capture")
        return
    await socket.accept()
    service = socket.app.state.voice
    acquired = False
    session = None
    try:
        # No audio or model work is accepted before explicit session consent.
        hello = await asyncio.wait_for(socket.receive_json(), timeout=10)
        if not isinstance(hello, dict) or hello.get("consent") is not True or hello.get("mode") not in {"manual", "wake"}:
            raise VoiceError("Session microphone consent and a valid listening mode are required")
        mode = hello["mode"]
        status = availability(service.settings)
        if not status["manual_available" if mode == "manual" else "wake_available"]:
            raise VoiceError(status["message"])
        if service.lock.locked():
            raise VoiceError("Another voice session is active. Stop it before starting a new one.")
        await service.lock.acquire()
        acquired = True
        session = await service.run(service.create_session, mode)
        await socket.send_json({"type": "state", "state": "recording" if mode == "manual" else "listening",
                                "message": "Speak now" if mode == "manual" else f"Listening for {service.settings.wake_phrase}"})
        while True:
            message = await asyncio.wait_for(socket.receive(), timeout=30)
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                command = json.loads(message["text"])
                if command.get("type") == "stop":
                    break  # Stop discards, never transcribes unsubmitted audio.
                if command.get("type") != "finish" or not session.capturing:
                    raise VoiceError("Unknown voice command")
                await socket.send_json({"type": "state", "state": "transcribing", "message": "Transcribing locally"})
                events = await service.run(session.finish)
            elif message.get("bytes") is not None:
                pcm = message["bytes"]
                if len(pcm) != 2560:
                    raise VoiceError("Invalid audio frame size")
                events = await service.run(session.process, pcm)
                if events and events[0]["type"] == "ready_to_transcribe":
                    await socket.send_json({"type": "state", "state": "transcribing", "message": "Transcribing locally"})
                    events = await service.run(session.finish)
            else:
                raise VoiceError("Invalid voice frame")
            for event in events:
                await socket.send_json(event)
            if session.finished:
                if mode == "manual":
                    break
                # Wait for explicit resume after chat so microphone audio cannot queue during inference.
                await socket.send_json({"type": "state", "state": "paused", "message": "Waiting for chat; wake listening will resume afterward"})
                while True:
                    resume = await asyncio.wait_for(socket.receive(), timeout=240)
                    if resume["type"] == "websocket.disconnect":
                        return
                    if resume.get("text"):
                        command = json.loads(resume["text"])
                        if command.get("type") == "stop":
                            return
                        if command.get("type") == "resume":
                            break
                    # Discard already-in-flight audio while paused; do not queue a new utterance.
                session.clear()
                await service.run(session.detector.reset)
                session = VoiceSession("wake", service.settings, service.recognizer, session.detector)
                await socket.send_json({"type": "state", "state": "listening", "message": f"Listening for {service.settings.wake_phrase}"})
    except WebSocketDisconnect:
        pass
    except VoiceError as exc:
        try:
            await socket.send_json({"type": "error", "message": str(exc)})
        except RuntimeError:
            pass
    except (ValueError, TimeoutError):
        try:
            await socket.send_json({"type": "error", "message": "Voice session stopped. Check consent, local model setup, microphone signal, or the selected mode."})
        except RuntimeError:
            pass
    except Exception:
        try:
            await socket.send_json({"type": "error", "message": "Local voice processing failed. Check voice dependencies/models and restart listening."})
        except RuntimeError:
            pass
    finally:
        if session:
            session.clear()
        if acquired:
            service.lock.release()
        try:
            await socket.close()
        except RuntimeError:
            pass

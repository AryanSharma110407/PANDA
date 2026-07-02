"""
PANDA — Perception Tools
============================
Handles sensory input for PANDA — microphone voice input via faster-whisper.

Built by Aryan 

Changes from Mark III:
  ❌ Removed: speech_recognition (Google API — online, high latency)
  ✅ Added:   faster-whisper "small" model (fully offline, low latency)

What you're learning here:
- faster-whisper — OpenAI Whisper reimplemented in CTranslate2 (4× faster)
- VAD (Voice Activity Detection) — detecting when someone is speaking
- PyAudio — recording raw PCM audio from the microphone
- The difference between online ASR (Google) and offline ASR (Whisper)
- Tool abstraction — hiding complexity behind simple functions
"""

import queue
import threading
import time

import numpy as np

try:
    import voice
except ImportError:
    class _VoiceStub:
        def interrupt(self):
            pass

        def is_speaking(self):
            return False

    voice = _VoiceStub()


WHISPER_MODEL_SIZE = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
LANGUAGE = "en"

SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
CHANNELS = 1
SILENCE_LIMIT = 1.2
ENERGY_THRESHOLD = 500

_whisper_model = None
_model_lock = threading.Lock()
_selected_device = None
_listener_singleton = None
_listener_lock = threading.Lock()


def _get_model():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    with _model_lock:
        if _whisper_model is None:
            try:
                # pyrefly: ignore [missing-import]
                from faster_whisper import WhisperModel

                print(
                    f"  \033[36m[Whisper] Loading '{WHISPER_MODEL_SIZE}' model "
                    f"({WHISPER_DEVICE}/{WHISPER_COMPUTE_TYPE})...\033[0m",
                    flush=True,
                )
                _whisper_model = WhisperModel(
                    WHISPER_MODEL_SIZE,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE,
                )
                print("  \033[36m[Whisper] Model ready.\033[0m", flush=True)
            except ImportError:
                print(
                    "  \033[31m[Whisper] faster-whisper not installed.\n"
                    "           Run: pip install faster-whisper\033[0m"
                )
    return _whisper_model


def list_microphones() -> list:
    try:
        import pyaudio

        pa = pyaudio.PyAudio()
        count = pa.get_device_count()
        mics = []
        for i in range(count):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                mics.append({"index": i, "name": info["name"]})
        pa.terminate()
        return mics
    except ImportError:
        print("  \033[31m[Mic] PyAudio not installed. Run: pip install pyaudio\033[0m")
        return []
    except Exception as e:
        return [{"index": -1, "name": f"Error listing mics: {e}"}]


def select_microphone(device_index=None, keyword=None) -> dict:
    global _selected_device
    mics = list_microphones()

    if device_index is not None:
        for mic in mics:
            if mic["index"] == device_index:
                _selected_device = device_index
                return {"status": "success", "device": mic["name"], "index": device_index}
        return {"status": "error", "message": f"Device index {device_index} not found."}

    if keyword:
        lowered = keyword.lower()
        for mic in mics:
            if lowered in mic["name"].lower():
                _selected_device = mic["index"]
                return {"status": "success", "device": mic["name"], "index": mic["index"]}
        return {"status": "error", "message": f"No microphone found matching '{keyword}'."}

    return {"status": "error", "message": "Provide either device_index or keyword."}


def _auto_detect_headset():
    global _selected_device
    headset_keywords = [
        "headset",
        "boat",
        "rockerz",
        "bluetooth",
        "airpod",
        "buds",
        "jbl",
        "sony",
        "bose",
        "usb mic",
        "external",
    ]

    for mic in list_microphones():
        name_lower = mic["name"].lower()
        for keyword in headset_keywords:
            if keyword in name_lower:
                _selected_device = mic["index"]
                print(
                    f"  \033[36m[Mic] Auto-detected: {mic['name']} "
                    f"(index {mic['index']})\033[0m"
                )
                return

    print("  \033[33m[Mic] Using default microphone\033[0m")


def _record_until_silence(timeout_seconds: float = 8.0, on_speech_start=None) -> np.ndarray | None:
    try:
        import pyaudio
    except ImportError:
        print("  \033[31m[Mic] PyAudio not installed. Run: pip install pyaudio\033[0m")
        return None

    pa = pyaudio.PyAudio()
    kwargs = {"input_device_index": _selected_device} if _selected_device is not None else {}

    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        **kwargs,
    )

    frames = []
    silence_chunks = 0
    speech_started = False
    silence_limit_chunks = int(SILENCE_LIMIT * SAMPLE_RATE / CHUNK_SIZE)
    wait_limit_chunks = int(timeout_seconds * SAMPLE_RATE / CHUNK_SIZE)
    waited = 0

    pre_speech_buffer = []
    consecutive_voice_chunks = 0

    try:
        import time
        start_time = time.time()
        while waited < wait_limit_chunks and (time.time() - start_time) < timeout_seconds:
            if not stream.is_active():
                break
            try:
                available = stream.get_read_available()
            except Exception:
                break
            if available < CHUNK_SIZE:
                time.sleep(0.01)
                continue

            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            arr = np.frombuffer(data, dtype=np.int16)
            rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
            
            pre_speech_buffer.append(data)
            if len(pre_speech_buffer) > 5:
                pre_speech_buffer.pop(0)

            if rms > ENERGY_THRESHOLD:
                consecutive_voice_chunks += 1
                if consecutive_voice_chunks >= 3:
                    speech_started = True
                    frames.extend(pre_speech_buffer)
                    if on_speech_start:
                        try:
                            on_speech_start()
                        except Exception:
                            pass
                    break
            else:
                consecutive_voice_chunks = 0
            waited += 1

        if not speech_started:
            return None

        start_record_time = time.time()
        max_record_time = 15.0  # max 15 seconds of speech to avoid infinite recording
        while (time.time() - start_record_time) < max_record_time:
            if not stream.is_active():
                break
            try:
                available = stream.get_read_available()
            except Exception:
                break
            if available < CHUNK_SIZE:
                time.sleep(0.01)
                continue

            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            frames.append(data)
            arr = np.frombuffer(data, dtype=np.int16)
            rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
            if rms < ENERGY_THRESHOLD:
                silence_chunks += 1
                if silence_chunks >= silence_limit_chunks:
                    break
            else:
                silence_chunks = 0

    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if not frames:
        return None

    raw = b"".join(frames)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _transcribe_audio(audio: np.ndarray | None) -> dict:
    if audio is None:
        return {"status": "error", "message": "No speech detected — timed out waiting."}

    if len(audio) < SAMPLE_RATE * 0.3:
        return {"status": "error", "message": "Audio too short — please speak for longer."}

    model = _get_model()
    if model is None:
        return {
            "status": "error",
            "message": "faster-whisper model failed to load. Check your installation.",
        }

    print("  \033[33m[Whisper] Transcribing...\033[0m", flush=True)

    try:
        segments, _info = model.transcribe(
            audio,
            language=LANGUAGE,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            return {
                "status": "error",
                "message": "Could not understand the audio. Please speak clearly.",
            }

        return {"status": "success", "text": text}
    except Exception as e:
        return {"status": "error", "message": f"Transcription failed: {e}"}


def listen_to_user() -> dict:
    global _selected_device

    if _selected_device is None:
        _auto_detect_headset()

    print("  \033[36m[Mic] Listening...\033[0m", flush=True)
    audio = _record_until_silence(timeout_seconds=8.0)
    return _transcribe_audio(audio)


class ContinuousListener:
    """
    System 1: always-on microphone listener.
    """

    def __init__(self):
        self.text_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> str:
        global _selected_device

        if self._thread is not None and self._thread.is_alive():
            return "🎤 Mic ON — already listening."

        if _selected_device is None:
            _auto_detect_headset()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker,
            name="panda-continuous-listener",
            daemon=True,
        )
        self._thread.start()
        return "🎤 Mic ON — continuous listening enabled."

    def stop(self) -> str:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return "🔇 Mic OFF — continuous listening disabled."

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _on_speech_start(self):
        # Temporarily disabled to avoid accidental silencing from background noise
        # if hasattr(voice, "is_speaking") and voice.is_speaking():
        #     voice.interrupt()
        pass

    def _worker(self):
        print("  \033[36m[Mic] Continuous listener active.\033[0m", flush=True)
        while not self._stop_event.is_set():
            audio = _record_until_silence(
                timeout_seconds=0.75,
                on_speech_start=self._on_speech_start,
            )
            result = _transcribe_audio(audio)
            if result["status"] == "success":
                text = result["text"]
                print(f"  \033[36m🎤 You said:\033[0m {text}", flush=True)
                self.text_queue.put(text)
            else:
                time.sleep(0.05)
        print("  \033[33m[Mic] Continuous listener stopped.\033[0m", flush=True)


def get_continuous_listener() -> ContinuousListener:
    global _listener_singleton
    with _listener_lock:
        if _listener_singleton is None:
            _listener_singleton = ContinuousListener()
    return _listener_singleton

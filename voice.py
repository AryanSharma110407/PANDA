"""
PANDA Voice System — Piper TTS  (Mark IV — Interruptible)
========================================================
Voice output uses Piper locally and supports fast interruption.

Key upgrades:
  - Kokoro replaced with PiperVoice from piper-tts
  - Audio format is int16 PCM at Piper's native sample rate (usually 22050 Hz)
  - Preemptive interruption stops playback within milliseconds
  - Public API is preserved: speak, speak_streaming, speak_blocking,
    enable, disable, wait_until_done, get_status, set_mood
"""

import io
import os
import queue
import re
import threading
import time
import warnings
import wave


from piper.voice import PiperVoice  #type: ignore
from piper.config import SynthesisConfig #type: ignore 

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

PIPER_MODEL_PATH = os.path.join(os.path.dirname(__file__), "en_GB-southern_english_female-low.onnx")
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "")
PIPER_USE_CUDA = os.getenv("PIPER_USE_CUDA", "0") == "1"
DEFAULT_SAMPLE_RATE = 22050
CHUNK_BYTES = 2048

_piper_voice = None
_pyaudio = None

_ENABLED = True
_MODEL_LABEL = os.path.basename(PIPER_MODEL_PATH)
_LENGTH_SCALE = 1.0

_STATE = {
    "speaking": False,
}

_SENTENCE_QUEUE: queue.Queue = queue.Queue()
_AUDIO_QUEUE: queue.Queue = queue.Queue(maxsize=2)
_STOP_SENTINEL = object()
_STOP_PLAYBACK = threading.Event()

_PAUSE_AFTER = {
    ".": 0.12,
    "!": 0.10,
    "?": 0.12,
    ";": 0.08,
    ",": 0.03,
    "": 0.0,
}

_FLUSH_CHARS = set(".!?;")
_MIN_PHRASE = 1

_synth_thread = None
_player_thread = None

_ANSI = re.compile(r"\033\[[0-9;]*m")
_EMOJI = re.compile(
    "["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F6FF"
    u"\U0001F1E0-\U0001F1FF"
    u"\U00002500-\U00002BEF"
    u"\U00002702-\U000027B0"
    u"\U000024C2-\U0001F251"
    u"\U0001f926-\U0001f937"
    u"\U00010000-\U0010ffff"
    u"\u2640-\u2642"
    u"\u2600-\u2B55"
    u"\u200d\u23cf\u23e9\u231a\ufe0f\u3030"
    "]+",
    flags=re.UNICODE,
)
_SENT_RE = re.compile(r"([.!?;])\s*")


def _clean(text: str) -> str:
    text = _ANSI.sub("", text)
    text = _EMOJI.sub("", text)
    text = re.sub(r"[*_#`|═─╔╗╚╝║╠╣╦╩╬•]", "", text)
    text = re.sub(r"([!?.]){2,}", r"\1", text)
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _split_phrases(text: str) -> list:
    connectors = {"and", "so", "but", "or", "yet", "now", "well", "also"}
    parts = _SENT_RE.split(text)
    phrases = []
    i = 0
    while i < len(parts):
        phrase = parts[i].strip()
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        if phrase and len(phrase) >= _MIN_PHRASE:
            phrases.append((phrase, punct))
        elif phrase and phrases:
            prev, prev_punct = phrases[-1]
            first_word = phrase.split()[0].lower() if phrase.split() else ""
            if first_word in connectors:
                phrases[-1] = (prev + prev_punct + "... " + phrase, "")
            else:
                phrases[-1] = (prev + prev_punct + " " + phrase, "")
    return phrases


def _get_pyaudio():
    global _pyaudio
    if _pyaudio is None:
        import pyaudio

        _pyaudio = pyaudio
    return _pyaudio


def _get_piper_voice():
    global _piper_voice
    if _piper_voice is not None:
        return _piper_voice

    kwargs = {}
    if PIPER_CONFIG_PATH:
        kwargs["config_path"] = PIPER_CONFIG_PATH
    
    # Modern Piper load can take use_cuda but sometimes errors on older/differing wrappers
    try:
        _piper_voice = PiperVoice.load(PIPER_MODEL_PATH, use_cuda=PIPER_USE_CUDA, **kwargs)
    except (TypeError, Exception):
        _piper_voice = PiperVoice.load(PIPER_MODEL_PATH, **kwargs)

    return _piper_voice


_synthesis_mode = None  # Will be set to 'chunks', 'stream_raw', 'stream_raw_no_len', 'buffer', or 'buffer_no_len'

def _detect_synthesis_mode(voice):
    global _synthesis_mode
    if _synthesis_mode is not None:
        return

    import inspect
    try:
        # Check if voice has synthesize_stream_raw
        if hasattr(voice, "synthesize_stream_raw"):
            raw_sig = inspect.signature(voice.synthesize_stream_raw)
            if "length_scale" in raw_sig.parameters:
                _synthesis_mode = "stream_raw"
            else:
                _synthesis_mode = "stream_raw_no_len"
            print(f"  \033[32m[Voice] Detected Piper API mode: {_synthesis_mode}\033[0m")
            return

        # Try to run a quick probe synthesis to find out which API version is active
        config = SynthesisConfig(length_scale=1.0)
        
        # Try the modern generator path
        try:
            res = voice.synthesize(".", config)
            iterator = iter(res)
            try:
                first_chunk = next(iterator)
                if hasattr(first_chunk, "audio_int16_bytes"):
                    _synthesis_mode = "chunks"
                    print(f"  \033[32m[Voice] Detected Piper API mode: {_synthesis_mode}\033[0m")
                    return
            except StopIteration:
                _synthesis_mode = "chunks"
                print(f"  \033[32m[Voice] Detected Piper API mode: {_synthesis_mode} (empty probe)\033[0m")
                return
        except Exception:
            pass

        # Try buffer path with length_scale
        try:
            import io
            buf = io.BytesIO()
            voice.synthesize(".", buf, length_scale=1.0)
            _synthesis_mode = "buffer"
            print(f"  \033[32m[Voice] Detected Piper API mode: {_synthesis_mode}\033[0m")
            return
        except Exception:
            pass

        # Try buffer path without length_scale
        try:
            import io
            buf = io.BytesIO()
            voice.synthesize(".", buf)
            _synthesis_mode = "buffer_no_len"
            print(f"  \033[32m[Voice] Detected Piper API mode: {_synthesis_mode}\033[0m")
            return
        except Exception:
            pass

    except Exception as e:
        print(f"  \033[31m[Voice] Warning: Error during Piper API detection: {e}. Falling back to default 'chunks'.\033[0m")
    
    # Ultimate fallback
    _synthesis_mode = "chunks"


def _extract_raw_pcm_if_wav(audio: bytes) -> bytes:
    if len(audio) > 0 and audio.startswith(b"RIFF"):
        import io, wave
        wav_buffer = io.BytesIO(audio)
        with wave.open(wav_buffer, "rb") as wav_file:
            return wav_file.readframes(wav_file.getnframes())
    return audio


def _get_sample_rate() -> int:
    voice = _get_piper_voice()
    config = getattr(voice, "config", None)
    return (
        getattr(config, "sample_rate", None)
        or getattr(voice, "sample_rate", None)
        or DEFAULT_SAMPLE_RATE
    )


def _synthesise(phrase: str) -> bytes:
    """
    Synthesises Piper audio and returns raw int16 PCM bytes.
    """
    voice = _get_piper_voice()
    _detect_synthesis_mode(voice)

    # 1. Chunks mode (Modern API)
    if _synthesis_mode == "chunks":
        config = SynthesisConfig(length_scale=_LENGTH_SCALE)
        chunks = voice.synthesize(phrase, config)
        return b"".join(chunk.audio_int16_bytes for chunk in chunks)

    # 2. Stream raw mode
    elif _synthesis_mode == "stream_raw":
        return b"".join(voice.synthesize_stream_raw(phrase, length_scale=_LENGTH_SCALE))

    # 3. Stream raw mode without length_scale
    elif _synthesis_mode == "stream_raw_no_len":
        return b"".join(voice.synthesize_stream_raw(phrase))

    # 4. Buffer mode
    elif _synthesis_mode == "buffer":
        import io
        wav_buffer = io.BytesIO()
        voice.synthesize(phrase, wav_buffer, length_scale=_LENGTH_SCALE)
        audio = wav_buffer.getvalue()
        return _extract_raw_pcm_if_wav(audio)

    # 5. Buffer mode without length_scale
    elif _synthesis_mode == "buffer_no_len":
        import io
        wav_buffer = io.BytesIO()
        voice.synthesize(phrase, wav_buffer)
        audio = wav_buffer.getvalue()
        return _extract_raw_pcm_if_wav(audio)

    raise RuntimeError(f"Unsupported synthesis mode: {_synthesis_mode}")


def _drain_queue(target_queue: queue.Queue):
    while True:
        try:
            item = target_queue.get_nowait()
        except queue.Empty:
            break
        else:
            target_queue.task_done()
            if item is _STOP_SENTINEL:
                break


def interrupt():
    """
    Stops current playback and clears queued speech.
    """
    _STOP_PLAYBACK.set()
    _STATE["speaking"] = False
    _drain_queue(_SENTENCE_QUEUE)
    _drain_queue(_AUDIO_QUEUE)


def is_speaking() -> bool:
    return _STATE["speaking"]


def _synth_worker():
    while True:
        try:
            item = _SENTENCE_QUEUE.get(timeout=0.1)
        except queue.Empty:
            continue

        if item is _STOP_SENTINEL:
            _SENTENCE_QUEUE.task_done()
            _AUDIO_QUEUE.put(_STOP_SENTINEL)
            break

        phrase, pause_char = item

        if _STOP_PLAYBACK.is_set():
            _SENTENCE_QUEUE.task_done()
            continue

        if _ENABLED and phrase:
            try:
                audio_bytes = _synthesise(phrase)
                if audio_bytes:
                    import numpy as np
                    rms = np.abs(np.frombuffer(audio_bytes, dtype=np.int16)).mean()
                    print(f"  \033[34m[Voice] Debug: Synthesized {len(audio_bytes)} bytes (Avg Amp: {rms:.1f})\033[0m")
            except Exception as e:
                print(f"  \033[31m[Voice] Piper error: {e}\033[0m")
                audio_bytes = b""

            if not _STOP_PLAYBACK.is_set():
                _AUDIO_QUEUE.put((audio_bytes, pause_char))
        else:
            _AUDIO_QUEUE.put((b"", pause_char))

        _SENTENCE_QUEUE.task_done()


def _player_worker():
    """
    Worker thread that reads raw synthesised PCM audio from _AUDIO_QUEUE and plays it.
    
    What you're learning here:
    - PortAudio / PyAudio Stream Recovery: Bluetooth headsets and sound devices on Windows frequently
      go to sleep or get disconnected, causing '[Errno -9999] Unanticipated host error'.
    - Re-entrant Stream Re-creation: When a write fails, closing both the stream and terminating
      the PyAudio context, then re-instantiating them, allows PyAudio to query the operating system's
      audio hardware afresh and seamlessly recover audio playback without restarting the assistant.
    - Defensive programming: Isolating device handles to on-demand lifecycle functions ensures that 
      errors in one play cycle do not leak into subsequent play cycles.
    """
    pa = _get_pyaudio()
    p = None
    stream = None
    sample_rate = _get_sample_rate()

    def get_stream():
        nonlocal p, stream
        if p is None:
            p = pa.PyAudio()
        if stream is None:
            try:
                stream = p.open(
                    format=pa.paInt16,
                    channels=1,
                    rate=sample_rate,
                    output=True,
                )
                return stream
            except Exception as default_err:
                print(f"  \033[33m[Voice] Failed to open default audio device: {default_err}. Scanning for fallback devices...\033[0m")
            
            # Scan all output devices
            for i in range(p.get_device_count()):
                try:
                    info = p.get_device_info_by_index(i)
                    if info.get("maxOutputChannels", 0) > 0:
                        print(f"  \033[36m[Voice] Trying fallback device [{i}]: {info['name']}...\033[0m")
                        stream = p.open(
                            format=pa.paInt16,
                            channels=1,
                            rate=sample_rate,
                            output_device_index=i,
                            output=True,
                        )
                        print(f"  \033[32m[Voice] Opened fallback device [{i}]: {info['name']}\033[0m")
                        return stream
                except Exception:
                    pass
            
            raise RuntimeError("Could not open default or any fallback audio output devices.")
        return stream

    def close_stream():
        nonlocal p, stream
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
            stream = None
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass
            p = None

    try:
        # Verify we can open the stream at least once on startup
        get_stream()
        print(f"  \033[32m[Voice] Piper Ready ({sample_rate}Hz)\033[0m")
    except Exception as e:
        print(f"  \033[31m[Voice] Player init error: {e}. Will attempt dynamic recovery on write.\033[0m")
        close_stream()

    try:
        while True:
            try:
                item = _AUDIO_QUEUE.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is _STOP_SENTINEL:
                _AUDIO_QUEUE.task_done()
                break

            audio_bytes, pause_char = item

            if audio_bytes and _ENABLED:
                _STATE["speaking"] = True
                try:
                    offset = 0
                    while offset < len(audio_bytes):
                        if _STOP_PLAYBACK.is_set() or not _ENABLED:
                            break
                        end = min(offset + CHUNK_BYTES, len(audio_bytes))
                        chunk = audio_bytes[offset:end]
                        
                        try:
                            active_stream = get_stream()
                            active_stream.write(chunk, exception_on_underflow=False)
                        except Exception as write_err:
                            print(f"  \033[31m[Voice] PyAudio write error: {write_err}. Re-opening stream...\033[0m")
                            close_stream()
                            # Retry writing the chunk once
                            try:
                                active_stream = get_stream()
                                active_stream.write(chunk, exception_on_underflow=False)
                            except Exception as retry_err:
                                print(f"  \033[31m[Voice] PyAudio write retry failed: {retry_err}\033[0m")
                                close_stream()
                                raise retry_err
                        
                        offset = end
                except Exception as e:
                    print(f"  \033[31m[Voice] PyAudio write failed for chunk: {e}\033[0m")
                    close_stream()

                _STATE["speaking"] = False

                if _STOP_PLAYBACK.is_set():
                    _STOP_PLAYBACK.clear()
                else:
                    pause = _PAUSE_AFTER.get(pause_char, 0.0)
                    if pause > 0:
                        time.sleep(pause)

            _AUDIO_QUEUE.task_done()
    except Exception as fatal_e:
        print(f"  \033[31m[Voice] Player thread died: {fatal_e}\033[0m")
    finally:
        _STATE["speaking"] = False
        close_stream()


def _ensure_pipeline():
    global _synth_thread, _player_thread

    if _synth_thread is None or not _synth_thread.is_alive():
        _synth_thread = threading.Thread(
            target=_synth_worker,
            name="panda-synth",
            daemon=True,
        )
        _synth_thread.start()

    if _player_thread is None or not _player_thread.is_alive():
        _player_thread = threading.Thread(
            target=_player_worker,
            name="panda-player",
            daemon=True,
        )
        _player_thread.start()


def speak(text: str):
    if not _ENABLED:
        return
    cleaned = _clean(text)
    if not cleaned:
        return
    _ensure_pipeline()
    phrases = _split_phrases(cleaned) or [(cleaned, "")]
    for phrase, punct in phrases:
        _SENTENCE_QUEUE.put((phrase, punct))


def speak_streaming(token_generator):
    if not _ENABLED:
        yield from token_generator
        return

    _ensure_pipeline()
    buf = ""

    for token in token_generator:
        yield token
        buf += token

        while True:
            best_pos = -1
            best_punct = ""
            for ch in _FLUSH_CHARS:
                idx = buf.find(ch)
                if idx != -1 and (best_pos == -1 or idx < best_pos):
                    best_pos = idx
                    best_punct = ch
            if best_pos == -1:
                break
            phrase = _clean(buf[:best_pos].strip())
            buf = buf[best_pos + 1 :].lstrip()
            if phrase and len(phrase) >= _MIN_PHRASE:
                _SENTENCE_QUEUE.put((phrase, best_punct))

    tail = _clean(buf.strip())
    if tail and len(tail) >= _MIN_PHRASE:
        _SENTENCE_QUEUE.put((tail, ""))


def speak_blocking(text: str):
    if not _ENABLED:
        return
    cleaned = _clean(text)
    if not cleaned:
        return
    _ensure_pipeline()
    phrases = _split_phrases(cleaned) or [(cleaned, "")]
    for phrase, punct in phrases:
        _SENTENCE_QUEUE.put((phrase, punct))
    _SENTENCE_QUEUE.join()
    _AUDIO_QUEUE.join()


def wait_until_done():
    _SENTENCE_QUEUE.join()
    _AUDIO_QUEUE.join()


def enable() -> str:
    global _ENABLED
    _ENABLED = True
    _ensure_pipeline()
    return "Voice enabled. Speaking from now on."


def disable() -> str:
    global _ENABLED
    _ENABLED = False
    interrupt()
    return "Voice disabled. Say 'voice on' to resume."


def is_enabled() -> bool:
    return _ENABLED


def get_status() -> str:
    state = "ON" if _ENABLED else "OFF"
    speaking = "YES" if is_speaking() else "NO"
    return (
        f"[Voice] Status : {state}\n"
        f"        Engine : Piper TTS\n"
        f"        Model  : {_MODEL_LABEL}\n"
        f"        Length : {_LENGTH_SCALE}\n"
        f"        Active : {speaking}"
    )


def set_voice(voice_name: str) -> str:
    global _MODEL_LABEL
    _MODEL_LABEL = voice_name
    return f"[Voice] Voice changed to: {voice_name}"


_MOOD_LENGTHS = {
    "tired": 1.20,
    "stressed": 1.10,
    "bored": 1.15,
    "excited": 0.92,
    "normal": 1.00,
}


def set_mood(mood: str) -> str:
    global _LENGTH_SCALE
    mood = mood.lower().strip()
    _LENGTH_SCALE = _MOOD_LENGTHS.get(mood, _MOOD_LENGTHS["normal"])
    return f"[Voice] Mood set to '{mood}' -> length_scale {_LENGTH_SCALE}"

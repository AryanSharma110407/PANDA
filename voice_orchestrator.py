# ─── Voice (Piper TTS) ───────────────────────────────────────────────────────
# voice.py is optional — PANDA works fine in text-only mode without it.

try:
    import voice
    _VOICE_AVAILABLE = True
except ImportError:
    _VOICE_AVAILABLE = False

    class _VoiceStub:
        def speak(self, *a, **kw):          pass
        def speak_streaming(self, gen):     yield from gen
        def speak_blocking(self, *a, **kw): pass
        def enable(self):                   return "Voice module not installed."
        def disable(self):                  return "Voice is already off (module not installed)."
        def get_status(self):               return "Voice module not installed."
        def is_enabled(self):               return False
        def wait_until_done(self):          pass
        def interrupt(self):                pass
        def is_speaking(self):              return False
        def set_mood(self, mood):           pass

    voice = _VoiceStub()



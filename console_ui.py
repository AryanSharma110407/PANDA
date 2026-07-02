import os, time, queue, threading
from voice_orchestrator import voice
# ═══════════════════════════════════════════════════════════════════════════════
# TYPEWRITER — word-aware streaming printer
# ═══════════════════════════════════════════════════════════════════════════════

def _stream_typewriter(generator, delay: float = 0.029, indent: int = 14):
    """
    Streams LLM output character-by-character with a typewriter effect, but
    wraps at *word* boundaries instead of letting the terminal cut mid-syllable.
    """
    try:
        term_w = os.get_terminal_size().columns
    except OSError:
        term_w = 80

    wrap_at   = term_w - 2
    re_indent = "  "

    col      = indent   #find cursor column
    word_buf = ""

    def _flush_word(word):
        nonlocal col
        if not word:
            return
        if col > 0 and col + len(word) > wrap_at:
            print()
            print(re_indent, end="", flush=True)
            col = len(re_indent)
        for ch in word:
            print(ch, end="", flush=True)
            time.sleep(delay)
        col += len(word)

    for chunk in generator:
        for char in chunk:
            if char == "\n":
                _flush_word(word_buf)
                word_buf = ""
                print()
                print(re_indent, end="", flush=True)
                col = len(re_indent)
            elif char == " ":
                _flush_word(word_buf)
                word_buf = ""
                if col > len(re_indent) or col == indent:
                    print(" ", end="", flush=True)
                    time.sleep(delay)
                    col += 1
            else:
                word_buf += char

    _flush_word(word_buf)
    print()


def _stream_and_collect(generator, delay: float = 0.029, indent: int = 14) -> str:
    """
    Streams LLM tokens to the terminal AND simultaneously speaks them
    via Piper TTS — JARVIS style.
    """
    collected = []

    voiced_gen = (
        voice.speak_streaming(generator)
        if hasattr(voice, "speak_streaming")
        else generator
    )

    import queue
    import threading
    token_queue = queue.Queue()

    def producer():
        for chunk in voiced_gen:
            collected.append(chunk)
            token_queue.put(chunk)
        token_queue.put(None)

    threading.Thread(target=producer, daemon=True).start()

    def _collecting_generator():
        while True:
            chunk = token_queue.get()
            if chunk is None:
                break
            yield chunk

    _stream_typewriter(_collecting_generator(), delay=delay, indent=indent)
    return "".join(collected)



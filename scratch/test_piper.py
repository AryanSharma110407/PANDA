import os
import io
import time
from piper.voice import PiperVoice
from piper.config import SynthesisConfig
import pyaudio

model = "en_US-lessac-medium.onnx"

try:
    voice = PiperVoice.load(model)
    
    # Check sample rate
    config = getattr(voice, "config", None)
    sr = getattr(config, "sample_rate", None) or getattr(voice, "sample_rate", None) or 22050
    print(f"Sample Rate detected: {sr}")

    phrase = "Hello! I am P.A.N.D.A (Proactive Autonomous Neural Directive Agent). Nice meeting you! What is it that you would like to assist you today"
    syn_config = SynthesisConfig(length_scale=1.0)

    print("Synthesizing...")
    chunks = list(voice.synthesize(phrase, syn_config))
    audio = b"".join(chunk.audio_int16_bytes for chunk in chunks)
    print(f"Total audio bytes: {len(audio)}")
    
    # Check if audio is non-zero
    if len(audio) > 0:
        import numpy as np
        samples = np.frombuffer(audio, dtype=np.int16)
        print(f"Max amplitude: {np.max(np.abs(samples))}")
        print(f"Mean amplitude: {np.mean(np.abs(samples))}")

    print("Initializing PyAudio...")
    pa = pyaudio.PyAudio()
    
    print(f"Default output device info: {pa.get_default_output_device_info()}")
    
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sr,
        output=True
    )
    
    print("Playing...")
    stream.write(audio)
    
    print("Finished playing.")
    stream.stop_stream()
    stream.close()
    pa.terminate()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

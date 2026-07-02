import pyaudio
import numpy as np

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paFloat32,
                channels=1,
                rate=24000,
                output=True)

# Generate a 1-second 440Hz sine wave as a test
duration = 1.0
f = 440.0
fs = 24000
t = np.linspace(0, duration, int(fs * duration), endpoint=False)
samples = (0.5 * np.sin(2 * np.pi * f * t)).astype(np.float32)

print("Playing sine wave...")
stream.write(samples.tobytes())
print("Done.")

stream.stop_stream()
stream.close()
p.terminate()

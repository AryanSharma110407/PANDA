import pyaudio
import numpy as np
import time

def list_devices(p):
    print("--- PyAudio Output Devices ---")
    default_out = p.get_default_output_device_info()
    print(f"Default Output Device: {default_out['name']} (Index {default_out['index']})")
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxOutputChannels'] > 0:
            print(f"[{i}] {info['name']} (Channels: {info['maxOutputChannels']})")
    print("------------------------------")

def play_test_tone(p):
    sample_rate = 22050
    duration = 2.0  # seconds
    frequency = 440.0  # Hz (A4)
    
    print(f"Playing a {frequency}Hz test tone for {duration} seconds on default device...")
    
    # Generate a sine wave
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Generate 16-bit PCM samples
    tone = np.sin(frequency * t * 2 * np.pi)
    # Scale to 16-bit range and ensure it's not too loud (0.3 volume)
    audio_data = np.int16(tone * 32767 * 0.3)
    
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=sample_rate,
                    output=True)
    
    stream.write(audio_data.tobytes())
    stream.stop_stream()
    stream.close()
    print("Playback finished.")

if __name__ == "__main__":
    p = pyaudio.PyAudio()
    try:
        list_devices(p)
        play_test_tone(p)
    except Exception as e:
        print(f"Error during audio test: {e}")
    finally:
        p.terminate()

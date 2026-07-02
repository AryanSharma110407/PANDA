import pyaudio
import numpy as np
import time

def test_speaker():
    print("Initializing PyAudio...")
    p = pyaudio.PyAudio()
    
    # List all output devices
    print("\n--- Available Output Devices ---")
    default_out = p.get_default_output_device_info()
    print(f"DEFAULT DEVICE: {default_out['name']} (Index {default_out['index']})")
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxOutputChannels"] > 0:
            print(f"[{i}] {info['name']}")
    print("--------------------------------\n")
    
    print("Generating a 1-second 440Hz Beep...")
    sample_rate = 44100
    t = np.linspace(0, 1, sample_rate, False)
    # Generate 440Hz sine wave, convert to 16-bit PCM
    audio = np.sin(440 * t * 2 * np.pi)
    audio_int16 = (audio * 32767).astype(np.int16).tobytes()

    print(f"Playing sound on default device: {default_out['name']} (Index {default_out['index']})...")
    try:
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=sample_rate,
                        output_device_index=default_out['index'],
                        output=True)
        stream.write(audio_int16)
        stream.stop_stream()
        stream.close()
        print("Done playing!")
    except Exception as e:
        print(f"Error playing sound: {e}")
        
    p.terminate()

if __name__ == "__main__":
    test_speaker()

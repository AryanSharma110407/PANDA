import torch
from kokoro import KPipeline

pipeline = KPipeline(lang_code='a')
generator = pipeline("test", voice='af_heart', speed=1.0)
for gs, ps, audio in generator:
    print(f"Type: {type(audio)}")
    print(f"Shape: {audio.shape if hasattr(audio, 'shape') else 'no shape'}")
    if hasattr(audio, 'device'):
        print(f"Device: {audio.device}")
    break

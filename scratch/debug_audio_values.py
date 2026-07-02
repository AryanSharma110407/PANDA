import torch
from kokoro import KPipeline
import numpy as np

pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M')
generator = pipeline("System test complete.", voice='af_heart', speed=1.0)

for gs, ps, audio in generator:
    if hasattr(audio, 'numpy'):
        audio_np = audio.detach().cpu().numpy()
    else:
        audio_np = audio
    
    print(f"Shape: {audio_np.shape}")
    print(f"Dtype: {audio_np.dtype}")
    print(f"Min: {audio_np.min()}")
    print(f"Max: {audio_np.max()}")
    print(f"Mean: {audio_np.mean()}")
    print(f"First 10 samples: {audio_np[:10]}")
    break

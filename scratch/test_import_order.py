import time
print("Starting import with torch first...", flush=True)
t0 = time.time()
try:
    import torch
    print(f"torch imported in {time.time()-t0:.2f}s", flush=True)
except Exception as e:
    print(f"torch import failed: {e}", flush=True)

t1 = time.time()
try:
    import paddleocr
    print(f"paddleocr imported in {time.time()-t1:.2f}s", flush=True)
    print(f"Total time: {time.time()-t0:.2f}s", flush=True)
except Exception as e:
    print(f"paddleocr import failed: {e}", flush=True)

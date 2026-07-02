import time
print("Starting import...", flush=True)
t0 = time.time()
try:
    import paddleocr
    print(f"Import completed successfully in {time.time()-t0:.2f} seconds", flush=True)
except Exception as e:
    print(f"Import failed after {time.time()-t0:.2f} seconds with: {e}", flush=True)

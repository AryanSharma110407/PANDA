import sys
import time

class SilentMock:
    def __init__(self, name="mock"):
        self.__name__ = name
    def __getattr__(self, name):
        # Allow nested attribute accesses to return another SilentMock
        return SilentMock(name)
    def __call__(self, *args, **kwargs):
        return SilentMock()

# Pre-populate sys.modules with our SilentMock to prevent real modelscope from being imported
sys.modules["modelscope"] = SilentMock("modelscope")
sys.modules["modelscope.hub"] = SilentMock("modelscope.hub")
sys.modules["modelscope.hub.errors"] = SilentMock("modelscope.hub.errors")

print("Starting paddleocr import with mocked modelscope...", flush=True)
t0 = time.time()
# pyrefly: ignore [missing-import]
import paddleocr
print(f"paddleocr imported successfully in {time.time()-t0:.2f} seconds!", flush=True)

import faulthandler
import threading
import time
import os

# Enable faulthandler to dump traceback to a file
log_file = open("scratch/import_traceback.txt", "w")

def dump_later():
    time.sleep(5)
    print("--- TIMEOUT REACHED, DUMPING TRACEBACK ---", flush=True)
    faulthandler.dump_traceback(file=log_file)
    log_file.close()
    # Force exit
    os._exit(1)

t = threading.Thread(target=dump_later)
t.daemon = True
t.start()

print("Starting import of paddleocr...", flush=True)
# pyrefly: ignore [missing-import]
import paddleocr
print("Import of paddleocr completed!", flush=True)

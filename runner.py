import sys
import time
import subprocess
import os
import atexit
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

LOCK_FILE = "bot.lock"

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        # Check if the process ID in the lock file is still running
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Check if process exists (Windows specific way roughly, or generic)
            # Utilizing psutil would be better but standard lib:
            # On Windows, we can't easily check PID existance without os.kill(pid, 0) which might not work or ctypes.
            # But let's just assume if the file exists and is recent, it's running.
            # actually better: just try to delete it? No, that breaks the running one.
            pass 
        except Exception:
            pass
            
        print(f"⚠️ {LOCK_FILE} detectado. ¿Ya se está ejecutando el bot?")
        try:
             os.remove(LOCK_FILE)
             print("⚠️ Lock file eliminado (asumiendo cierre inesperado anterior).")
        except PermissionError:
             print("❌ ERROR CRÍTICO: El bot YA ESTÁ CORRIENDO en otra ventana.")
             print("❌ Cierra esta ventana y usa la existente.")
             sys.exit(1)

    # Create lock
    try:
        # On Windows, opening with 'x' (exclusive creation) isn't atomic locking against other processes opening it?
        # A better way is to keep the file OPEN.
        global lock_handle
        lock_handle = open(LOCK_FILE, 'w')
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
    except IOError:
        print("❌ ERROR: No se pudo crear el archivo lock.")
        sys.exit(1)

def release_lock():
    global lock_handle
    if lock_handle:
        lock_handle.close()
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except:
            pass

class RestartHandler(FileSystemEventHandler):
    def __init__(self, process):
        self.process = process
        self.last_restart = 0

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            # Debounce restarts (wait at least 2 seconds between restarts)
            if time.time() - self.last_restart < 2:
                return
            
            self.last_restart = time.time()
            print(f"\n🔄 Detectado cambio en {event.src_path}. Reiniciando bot...")
            try:
                self.process.terminate()
                self.process.wait()
            except:
                pass
            self.process = subprocess.Popen([sys.executable, "main.py"])

def start_bot():
    acquire_lock()
    atexit.register(release_lock)
    
    print("🚀 Iniciando bot con auto-reload... (Singleton Mode)")
    process = subprocess.Popen([sys.executable, "main.py"])
    event_handler = RestartHandler(process)
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
            if process.poll() is not None:
                # Bot crashed or stopped
                print("⚠️ El bot se detuvo. Reiniciando en 5 segundos...")
                time.sleep(5)
                process = subprocess.Popen([sys.executable, "main.py"])
                event_handler.process = process
    except KeyboardInterrupt:
        observer.stop()
        try:
            process.terminate()
        except:
            pass
    finally:
        observer.join()
        release_lock()

if __name__ == "__main__":
    start_bot()

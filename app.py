import threading, time
from project import app
from waitress import serve
from project.util.email import detect_bounce

# thread = threading.Thread(target=detect_bounce, args=(30,))
# thread.daemon = True
# thread.start()

if __name__ == "__main__":
   serve(app, host="0.0.0.0", port=5000, threads=8)

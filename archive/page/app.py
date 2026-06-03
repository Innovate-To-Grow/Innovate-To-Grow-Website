import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

from project import app
from waitress import serve

if __name__ == "__main__":
    import sys
    if "--debug" in sys.argv:
        app.run(debug=True, host="0.0.0.0", port=5001)
    else:
        serve(app, host="0.0.0.0", port=5001, threads=8)

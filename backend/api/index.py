import sys
from pathlib import Path

# Ensure backend root is in sys.path so 'app' imports cleanly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app as _app

# Explicit top-level assignments required by Vercel static AST parser
app = _app
application = app
handler = app

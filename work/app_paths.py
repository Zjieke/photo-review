"""Keep bundled, read-only code separate from the user's writable local data.

The launcher sets PHOTO_REVIEW_DATA_DIR for installed builds.  An unset variable
keeps the existing source-checkout layout for developers.  Importing this module
does not create files or touch the Photos library.
"""
import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_ROOT = Path(os.environ.get('PHOTO_REVIEW_DATA_DIR') or PROJECT_DIR).expanduser().resolve()
OUT = DATA_ROOT / 'outputs'
STATE_DIR = DATA_ROOT / 'work'
MODELS_DIR = STATE_DIR / 'models'


def ensure_data_dirs(data_root=None):
    """Create only the runtime directories, and surface permission errors early."""
    root = DATA_ROOT if data_root is None else Path(data_root).expanduser().resolve()
    for path in (root / 'outputs', root / 'work', root / 'work' / 'models'):
        path.mkdir(parents=True, exist_ok=True)
    return root

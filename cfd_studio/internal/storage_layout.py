"""Keep compatibility storage out of the application folder on clean installations."""
from pathlib import Path


def compatibility_folder(here, legacy, runtime_name):
    """Retain populated legacy folders; never move or discard data at startup."""
    here = Path(here)
    old = here / legacy
    if old.is_dir() and any(old.iterdir()):
        return str(old)
    return str(here / '_runtime' / runtime_name)

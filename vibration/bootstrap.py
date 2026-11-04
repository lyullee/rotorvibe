from pathlib import Path
import sys
import os

PACKAGE_ROOT=Path(__file__).resolve().parents[1]
SOURCE_CHECKOUT=(PACKAGE_ROOT/'pyproject.toml').is_file() and (PACKAGE_ROOT/'vibration').is_dir()
PROJECT = Path(os.environ.get('VIBRATION_PROJECT_HOME',PACKAGE_ROOT if SOURCE_CHECKOUT else Path.cwd()))
# The existing project runtime may use locally bundled scientific dependencies.
LOCAL_DEPS = PROJECT / 'tmp' / 'validation_deps'
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))
state_root=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/state'))/'vibration-analysis-toolkit'
RUNTIME = Path(os.environ.get('VIBRATION_RUNTIME_HOME',PROJECT/'runtime' if SOURCE_CHECKOUT or 'VIBRATION_PROJECT_HOME' in os.environ else state_root))


# Backward-compatibility shim.
# paths.py has moved to src/utils/paths.py.
# All existing imports (from paths import get_paths) continue to work unchanged.
from utils.paths import (  # noqa: F401
    DashboardPaths,
    get_paths,
    ConfigPaths,
    get_config,
    _PROJECT_ROOT,
)

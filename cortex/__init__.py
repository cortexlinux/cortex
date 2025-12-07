from importlib import metadata

from .cli import main
from .packages import PackageManager, PackageManagerType

try:
    __version__ = metadata.version("cortex-linux")
except metadata.PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__", "main", "PackageManager", "PackageManagerType"]
__version__ = "0.1.0"

__all__ = ["main", "PackageManager", "PackageManagerType"]

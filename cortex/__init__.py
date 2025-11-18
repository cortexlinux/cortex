from importlib import metadata

try:
    __version__ = metadata.version("cortex-linux")
except metadata.PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]

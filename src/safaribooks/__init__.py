"""safaribooks -- download O'Reilly books as EPUB files."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("safaribookshelf")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
finally:
    del version, PackageNotFoundError

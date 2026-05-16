from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

from cmodel import types as types
from cmodel.base import CCountedBy as CCountedBy
from cmodel.base import CEncoded as CEncoded
from cmodel.base import CFormat as CFormat
from cmodel.base import CModel as CModel

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # nocov
    __version__ = "0.0.0"

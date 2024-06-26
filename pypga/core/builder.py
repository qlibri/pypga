import logging
import shutil
from abc import ABC, abstractmethod

from .common import empty_path
from .migen import AutoMigenModule
from .settings import settings

logger = logging.getLogger(__name__)
builder_registry = {}


def get_builder(board, module_class):
    return builder_registry[board](module_class)


class BaseBuilder(ABC):
    board = None

    def __init_subclass__(cls):
        if cls.board is None:
            raise ValueError(
                f"{cls.__name__} is a subclass of BaseBuilder "
                f"but does not define the ``board`` attribute."
            )
        builder_registry[cls.board] = cls

    def _get_result_path(self):
        return (
            settings.result_path
            / str(self.board)
            / self.module_class.__name__
            / self.hash
        ).resolve()

    def _get_build_path(self):
        return (
            settings.build_path / str(self.board) / self.module_class.__name__
        ).resolve()

    @property
    def result_exists(self):
        logger.debug(f"Looking for existing build in {self.result_path}.")
        return self.result_path.is_dir()

    _build_results = []

    def copy_results(self):
        """Copy all build results to a persistent folder"""
        empty_path(self.result_path)
        for result in self._build_results:
            shutil.copy(self.build_path / result, self.result_path / result)
        logger.debug(
            f"Copied all build artifacts for new build of "
            f"{self.module_class.__name__} for {self.board} "
            f"with hash {self.hash} to {self.result_path}: {self._build_results}"
        )

    def __init__(self, module_class):
        self.module_class = module_class
        self.hash = self._get_hash()
        self.result_path = self._get_result_path()
        self.build_path = self._get_build_path()

    def build(self):
        empty_path(self.build_path)
        self._build()

    # board-specific methods

    @abstractmethod
    def _get_hash(self):
        """Returns a hash for the design, without building the actual design or requiring a build folder."""
        pass

    @abstractmethod
    def _build(self):
        """The actual steps required for building this design."""
        pass

import os
from abc import ABC, abstractmethod


class BaseFileHandler(ABC):
    @abstractmethod
    def extract_texts(self, file_path: str) -> list[dict]:
        """Extract translatable texts from a file.

        Returns a list of dicts with at least:
            - 'text': the text string to translate
            - 'location': handler-specific location metadata
        """
        pass

    @abstractmethod
    def apply_translations(
        self, file_path: str, translations: list[dict], output_path: str
    ):
        """Apply translated texts back to the file structure and save."""
        pass

    @classmethod
    @abstractmethod
    def supported_extensions(cls) -> list[str]:
        pass


# Handler registry
_HANDLERS: dict[str, type[BaseFileHandler]] = {}


def register_handler(handler_class: type[BaseFileHandler]):
    for ext in handler_class.supported_extensions():
        _HANDLERS[ext.lower()] = handler_class
    return handler_class


def get_handler(file_path: str) -> BaseFileHandler | None:
    ext = os.path.splitext(file_path)[1].lower()
    handler_class = _HANDLERS.get(ext)
    if handler_class:
        return handler_class()
    return None


def get_supported_extensions() -> list[str]:
    return sorted(_HANDLERS.keys())

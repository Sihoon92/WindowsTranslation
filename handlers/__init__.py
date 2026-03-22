# Import all handlers to trigger registration
from handlers import text_handler  # noqa: F401
from handlers import json_handler  # noqa: F401
from handlers import word_handler  # noqa: F401
from handlers import pptx_handler  # noqa: F401
from handlers import excel_handler  # noqa: F401
from handlers import pdf_handler  # noqa: F401
from handlers.base import get_handler, get_supported_extensions  # noqa: F401

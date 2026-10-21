"""
adapters/ — one module per provider (CLAUDE.md: provider chains are
declarative config, not code paths). Each module registers its adapter(s)
with `registry.registry` at import time (see `adapters/base.py` for the
interface) and `app.py` imports every adapter module once at startup so
registration happens before the first request.

"""

from . import ordbank  # noqa: F401
from . import kaikki  # noqa: F401
from . import nst  # noqa: F401
from . import kaikki_ipa  # noqa: F401
from . import ordbokene  # noqa: F401
from . import ipadict  # noqa: F401
from . import wikipron  # noqa: F401
from . import kaikki_tts  # noqa: F401
from . import google_translate  # noqa: F401
from . import bing_translate  # noqa: F401
from . import deepl  # noqa: F401
from . import libretranslate  # noqa: F401
from . import hf_whisper  # noqa: F401
from . import not_configured  # noqa: F401

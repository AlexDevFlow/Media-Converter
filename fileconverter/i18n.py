"""gettext-based translation setup for File Converter."""

from __future__ import annotations
import gettext as _gettext
import os
import sys
from pathlib import Path

DOMAIN = "fileconverter"

# Languages we ship .mo files for, paired with their native-language display name.
# The order here controls the order shown in the settings dropdown.
SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "System default"),
    ("en_US", "English"),
    ("ar_EG", "العربية"),
    ("cs_CZ", "Čeština"),
    ("de_DE", "Deutsch"),
    ("el_GR", "Ελληνικά"),
    ("es_ES", "Español"),
    ("fa_IR", "فارسی"),
    ("fr_FR", "Français"),
    ("he_IL", "עברית"),
    ("hi_IN", "हिन्दी"),
    ("hu_HU", "Magyar"),
    ("id_ID", "Bahasa Indonesia"),
    ("it_IT", "Italiano"),
    ("ja_JP", "日本語"),
    ("ko_KR", "한국어"),
    ("nl_NL", "Nederlands"),
    ("pl_PL", "Polski"),
    ("pt_BR", "Português (Brasil)"),
    ("pt_PT", "Português"),
    ("ro_RO", "Română"),
    ("ru_RU", "Русский"),
    ("sr_Cyrl", "Српски"),
    ("sr_Latn", "Srpski"),
    ("sv_SE", "Svenska"),
    ("th_TH", "ไทย"),
    ("tr_TR", "Türkçe"),
    ("uk_UA", "Українська"),
    ("vi_VN", "Tiếng Việt"),
    ("zh_CN", "简体中文"),
    ("zh_TW", "繁體中文"),
]

LANGUAGE_CODES = [code for code, _label in SUPPORTED_LANGUAGES]


def _candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    paths: list[Path] = []

    # PyInstaller bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / "locales")

    # Shipped inside the package (works for source checkouts and pip installs)
    paths.append(here / "locales")
    # Older layouts kept locales/ next to the package
    paths.append(here.parent / "locales")

    # User install
    paths.append(Path.home() / ".local" / "share" / "locale")

    # System install
    paths.append(Path("/usr/local/share/locale"))
    paths.append(Path("/usr/share/locale"))

    return paths


# glibc locale @modifier → ISO-15924 script suffix we ship (sr@latin → sr_Latn)
_SCRIPT_MODIFIERS = {"latin": "Latn", "cyrillic": "Cyrl"}


def detect_system_language() -> str | None:
    """Return the best-matching supported locale code for the current system,
    or None if the system language isn't one we ship.

    Reads LANGUAGE / LC_ALL / LC_MESSAGES / LANG in order, matches the first
    component against our SUPPORTED_LANGUAGES list (full code first, then the
    two-letter prefix against any variant we ship).
    """
    # An ordered list, not a set: for a bare prefix like "zh"/"pt"/"sr" the
    # first shipped variant must win deterministically. A set iterates in a
    # hash-randomised order, so "zh" flipped between Simplified and Traditional
    # from launch to launch.
    supported = [code for code in LANGUAGE_CODES if code != "auto"]
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if not val:
            continue
        for item in val.split(":"):
            base = item.split(".")[0]
            # Honour a script modifier if we ship that exact variant
            # (sr@latin → sr_Latn), else drop it.
            modifier = base.split("@")[1] if "@" in base else ""
            code = base.split("@")[0]
            if not code:
                continue
            if code in supported:
                return code
            if modifier:
                script = _SCRIPT_MODIFIERS.get(modifier.lower(), modifier.capitalize())
                want = f"{code.split('_')[0]}_{script}"
                if want in supported:
                    return want
            prefix = code.split("_")[0]
            for s in supported:
                if s.split("_")[0] == prefix:
                    return s
    return None


def _find_localedir() -> str | None:
    for p in _candidates():
        try:
            if p.is_dir() and any(p.glob(f"*/LC_MESSAGES/{DOMAIN}.mo")):
                return str(p)
        except OSError:
            continue
    return None


def _make_translator(lang: str | None = None):
    """Build a translator. `lang` is a locale code (e.g. 'it_IT') or None for system default."""
    localedir = _find_localedir()
    languages = [lang] if lang else None
    try:
        return _gettext.translation(
            DOMAIN, localedir=localedir, languages=languages, fallback=True
        )
    except OSError:
        return _gettext.NullTranslations()


_translator = _make_translator()


def init(lang: str | None = None) -> None:
    """Reinitialize the translator. Pass a locale code, or 'auto'/None for system default.

    Any `_()` calls after this point use the new language. Widgets already
    constructed with the old translations keep their old labels — re-create
    them if you need a live switch.
    """
    global _translator
    if lang in (None, "", "auto"):
        _translator = _make_translator(None)
    else:
        _translator = _make_translator(lang)


def gettext(message: str) -> str:
    return _translator.gettext(message)


# Short alias, conventional name for translated strings.
_ = gettext

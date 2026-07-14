"""Platform integration — dispatches to the Linux or macOS installer.

Import `install_hint`, `run_install`, `run_uninstall`, `is_installed` from
here rather than from a platform module, so conversion backends and the CLI
stay platform-agnostic.
"""

from __future__ import annotations
import sys

if sys.platform == "darwin":
    from fileconverter.integration.macos import (  # noqa: F401
        install_hint, is_installed, run_install, run_uninstall,
    )
else:
    from fileconverter.integration.install import (  # noqa: F401
        install_hint, is_installed, run_install, run_uninstall,
    )


def main() -> None:
    """Console-script entry point (`fileconverter-install`) — dispatches to
    the platform installer, so a pip install on macOS never runs the Linux
    flow."""
    if "--uninstall" in sys.argv:
        run_uninstall()
    else:
        run_install()


__all__ = ["install_hint", "is_installed", "main", "run_install", "run_uninstall"]

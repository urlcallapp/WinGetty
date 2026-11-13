"""Automated intake of winget-downloaded packages into WinGetty.

Reads the YAML manifest that `winget download` writes next to every
downloaded installer and registers the package, version and installers in
WinGetty, either directly against the database (local mode, run on the
WinGetty host) or through the WinGetty REST API (API mode, run anywhere).
"""

__version__ = "1.0.0"

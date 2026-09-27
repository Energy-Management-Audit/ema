"""Choose an OS keyring without relying on frozen distribution entry points."""

import sys

import keyring
from keyring.backends import fail, macOS
from keyring.backends.Windows import WinVaultKeyring


def install_keyring() -> None:
    if sys.platform == "win32":
        backend = WinVaultKeyring()
    elif sys.platform == "darwin":
        backend = macOS.Keyring()
    else:
        backend = fail.Keyring()
    keyring.set_keyring(backend)

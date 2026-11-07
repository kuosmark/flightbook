"""Load the configured signing key or manage a private key for local use."""

import os
from pathlib import Path
import secrets


def load_key(instance_path, *, create=False):
    """Only explicit initialization may create a key. Never replace an existing key."""
    configured = os.environ.get("FLIGHTBOOK_SECRET_KEY")
    if configured:
        return configured

    directory = Path(instance_path)
    path = directory / "session.key"
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as target:
                target.write(secrets.token_bytes(32))

    try:
        key = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(key) != 32:
        raise RuntimeError("Invalid local session key. Restore instance/session.key from backup.")
    return key

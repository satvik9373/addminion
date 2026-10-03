"""
Environment loader
Loads .env file into os.environ. No external dependencies.
"""

import os
from pathlib import Path


def load_dotenv(path: str = None) -> bool:
    """
    Load a .env file into os.environ if present.
    Returns True if a file was loaded, False otherwise.
    Does NOT override already-set environment variables.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

    env_path = Path(path)
    if not env_path.exists():
        return False

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()

            # Strip surrounding quotes if present
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]

            # Support simple # inline comments (but not in quoted values)
            if value and not (value[0] in ('"', "'")):
                value = value.split(' #')[0].strip()

            if key and key not in os.environ:
                os.environ[key] = value

    return True

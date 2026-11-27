#!/usr/bin/env python
"""Django command-line utility for Kaam Madad.

Defaults to development settings ("test" defaults to config.settings.test). Override with --settings=... or the
DJANGO_SETTINGS_MODULE environment variable.
"""

import os
import sys


def main() -> None:
    # "manage.py test" must never pick up real provider keys from .env, so it defaults to test settings.
    default = "config.settings.test" if sys.argv[1:2] == ["test"] else "config.settings.development"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Activate the backend virtual environment "
            "(see README.md) and install backend/requirements.txt."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

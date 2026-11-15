"""Plugins: optional features that live in their own folder, `app/plugins/<name>/` (see README.md here).

The app works without any. A plugin is a Python package whose `__init__.py` may define any of these names:

- `router`: an APIRouter, added to the app. All its routes need a logged-in user: the app checks that itself.
- `public_router`: an APIRouter for the rare routes that must work without a login. Nothing is checked for these.
- `STARTUP_SQL`: a list of SQL statements, run at startup after the tables exist (after the app's own list).
- `startup()`: async, called once before the app takes requests (e.g. to start a background task).
- `shutdown()`: async, called when the app stops.
- `delete_user(db, user_id)`: async, called before an admin deletes an account.

Tables a plugin declares (subclasses of `db.Base`) are created with the app's own.
"""

import importlib
import pkgutil
from types import ModuleType

loaded: list[ModuleType] = []


def load() -> None:
    """Import every plugin folder. Called once by main.py, before the app is built."""
    for module in pkgutil.iter_modules(__path__):
        if module.ispkg:
            loaded.append(importlib.import_module(f"{__name__}.{module.name}"))


def each(name: str) -> list:
    """Collect one hook from the plugins that define it.

    Args:
        name: The hook, e.g. "router" or "startup".

    Returns:
        The value of that name in every loaded plugin that has it.
    """
    return [getattr(plugin, name) for plugin in loaded if hasattr(plugin, name)]

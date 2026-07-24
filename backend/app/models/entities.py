"""ORM entities — re-exports the single module `_entities_all`.

Domain-split facade files were removed; import via `app.models` or this package.
"""

from app.models._entities_all import *  # noqa: F403

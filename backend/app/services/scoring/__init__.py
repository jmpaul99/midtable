"""Scoring package — stable import path for the engine.

Implementation lives in `engine.py` as a single module (not split further yet).
Import from `app.services.scoring` only.
"""

from app.services.scoring.engine import *  # noqa: F403

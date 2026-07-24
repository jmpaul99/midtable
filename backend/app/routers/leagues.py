"""Compatibility shim — prefer leagues_core / invites / league_ops / league_reads."""
from app.routers.leagues_core import router

__all__ = ["router"]

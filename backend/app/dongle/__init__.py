"""AutoBrain Dongle Server — firmware release & distribution (AUT-1673).

Merged into backend as sub-app on :8002. Owns: firmware manifests, MinIO
signed blob URLs, serial-number whitelist, paid-account gate (delegated to
the AutoBrain backend), and the ops web GUI.
"""

from .main import app

__all__ = ["app"]
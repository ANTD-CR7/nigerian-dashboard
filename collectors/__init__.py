"""NPEDATA automated data collectors.

Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
"""
from .base import Connector, normalize
from .world_bank import WorldBankConnector
from .sources_scaffold import CBNConnector, NBSConnector

__all__ = ["Connector", "normalize", "WorldBankConnector", "CBNConnector", "NBSConnector"]

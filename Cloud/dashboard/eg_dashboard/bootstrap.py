"""Uvicorn entrypoint over the server's existing EvidenceGuard source tree."""
import importlib
from .bridge import attach, instrument, load_ops

ops, native = load_ops()
instrument(ops, native)
app = attach(importlib.import_module('evidenceguard.app').app, ops, native)

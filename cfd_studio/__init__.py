"""Stable imports while implementation files live in the internal folder."""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parent / 'internal'))

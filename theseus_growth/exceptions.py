"""Exceptions raised by the Theseus V1 DataFrame API."""


class TheseusError(Exception):
    """Base class for errors raised by Theseus."""


class SchemaError(TheseusError, ValueError):
    """A source DataFrame does not satisfy its public schema."""


class TimeAxisError(TheseusError, ValueError):
    """Periods do not form a supported, internally consistent time axis."""


class BroadcastError(TheseusError, ValueError):
    """A cohort cannot be broadcast with the supplied curve."""

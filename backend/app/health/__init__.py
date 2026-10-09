"""The health model: configuration, scoring and triggers, all pure.

Nothing in this package reads the database or the clock; the services that
load signals and store snapshots and flags call into it.
"""

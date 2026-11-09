"""Errors whose message is complete on its own; the CLI prints them without a
traceback."""


class ConfigError(ValueError):
    """paper.toml, a facts sidecar or the frozen-facts file is invalid."""

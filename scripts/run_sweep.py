"""Backward-compatible wrapper for :mod:`crosfed.cli.sweep`."""

from crosfed.cli.sweep import combinations, main, normalize_threshold

__all__ = ["combinations", "normalize_threshold", "main"]


if __name__ == "__main__":
    main()

"""Backward-compatible wrapper for :mod:`crosfed.cli.adversarial`."""

from crosfed.cli.adversarial import expect_rejection, main, run_suite

__all__ = ["expect_rejection", "run_suite", "main"]


if __name__ == "__main__":
    main()

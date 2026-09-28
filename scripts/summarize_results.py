"""Backward-compatible wrapper for :mod:`crosfed.cli.summarize`."""

from crosfed.cli.summarize import aggregate_runs, load_run, main, write_outputs

__all__ = ["load_run", "aggregate_runs", "write_outputs", "main"]


if __name__ == "__main__":
    main()

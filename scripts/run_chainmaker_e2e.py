"""Backward-compatible wrapper for :mod:`crosfed.cli.chainmaker_e2e`."""

from crosfed.cli.chainmaker_e2e import find_metric, find_request_id, main

__all__ = ["find_metric", "find_request_id", "main"]


if __name__ == "__main__":
    main()

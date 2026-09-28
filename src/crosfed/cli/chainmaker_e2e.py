"""CLI adapter for the ChainMaker end-to-end check."""

from crosfed.integrations.chainmaker.e2e import find_metric, find_request_id, main

__all__ = ["find_metric", "find_request_id", "main"]

if __name__ == "__main__":
    main()

"""CLI adapter for the version-isolated ChainMaker bridge."""

from crosfed.integrations.chainmaker.bridge import main

__all__ = ["main"]

if __name__ == "__main__":
    main()

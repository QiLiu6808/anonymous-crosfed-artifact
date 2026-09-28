"""CLI adapter for experiment-matrix generation."""

from crosfed.experiments.sweep import combinations, main, normalize_threshold

__all__ = ["combinations", "normalize_threshold", "main"]

if __name__ == "__main__":
    main()

"""CLI adapter for adversarial protocol checks."""

from crosfed.experiments.adversarial import expect_rejection, main, run_suite

__all__ = ["expect_rejection", "run_suite", "main"]

if __name__ == "__main__":
    main()

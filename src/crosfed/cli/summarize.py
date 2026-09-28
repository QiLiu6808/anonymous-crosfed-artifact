"""CLI adapter for result aggregation."""

from crosfed.experiments.reporting import aggregate_runs, load_run, main, write_outputs

__all__ = ["load_run", "aggregate_runs", "write_outputs", "main"]

if __name__ == "__main__":
    main()

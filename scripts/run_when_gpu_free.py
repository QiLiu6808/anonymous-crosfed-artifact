from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


def gpu_state(index: int) -> tuple[int, int]:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            f"--id={index}",
            "--query-gpu=memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    memory, utilization = (int(part.strip()) for part in output.split(","))
    return memory, utilization


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--max-memory-mib", type=int, default=500)
    parser.add_argument("--max-utilization", type=int, default=10)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--max-wait-seconds", type=int, default=21_600)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        parser.error("a command is required after --")

    started = time.monotonic()
    while True:
        memory, utilization = gpu_state(args.gpu)
        now = datetime.now(timezone.utc).isoformat()
        print(
            f"[{now}] gpu={args.gpu} memory_mib={memory} utilization={utilization}%",
            flush=True,
        )
        if memory < args.max_memory_mib and utilization < args.max_utilization:
            break
        if time.monotonic() - started >= args.max_wait_seconds:
            print("GPU wait timed out without launching the experiment", file=sys.stderr)
            raise SystemExit(75)
        time.sleep(args.poll_seconds)

    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    print(f"GPU is free; launching: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, env=environment, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()


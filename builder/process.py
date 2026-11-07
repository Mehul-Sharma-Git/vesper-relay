"""Launch bounded jobs and stop their process group if the runner disappears."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def stop_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def run_process(command, *, cwd, input_text, env, log, timeout, on_start=lambda _: None):
    read_fd, write_fd = os.pipe()
    supervisor = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                  str(os.getpid()), str(write_fd), *command]
    with os.fdopen(read_fd, "rb") as result, log.open("wb") as output:
        try:
            process = subprocess.Popen(supervisor, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True, pass_fds=(write_fd,))
        finally:
            os.close(write_fd)
        with process as child:
            try:
                on_start(child.pid)
                child.communicate(input_text.encode(), timeout=timeout)
                status = result.read()
                return int(status) if status.isdigit() else 125
            except subprocess.TimeoutExpired:
                stop_group(child.pid, signal.SIGKILL)
                child.wait()
                return 124
            finally:
                stop_group(child.pid, signal.SIGKILL)


def supervise(parent, status_fd, command):
    try:
        child = subprocess.Popen(command)
    except OSError as exc:
        print(exc, file=sys.stderr)
        status = 127
    else:
        while True:
            if os.getppid() != parent:
                os.killpg(os.getpgrp(), signal.SIGKILL)
            status = child.poll()
            if status is not None:
                break
            time.sleep(0.05)
    try:
        os.write(status_fd, str(status if status >= 0 else 128 - status).encode("ascii"))
    finally:
        os.killpg(os.getpgrp(), signal.SIGKILL)


if __name__ == "__main__":
    supervise(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3:])

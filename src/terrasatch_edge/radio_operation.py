"""CLI lifetime lease and cancellation, including calibration before service start."""

from functools import wraps
import signal

import typer

from .config import get_paths
from .radio_lock import ReceiverLock


def radio_operation(function):
    @wraps(function)
    def run(*args, **kwargs):
        previous = {}
        try:
            with ReceiverLock(name="operation.lock"):
                get_paths().state_dir.joinpath("radio-stop.request").unlink(missing_ok=True)
                def cancel(*_):
                    raise KeyboardInterrupt
                for sig in (signal.SIGINT, signal.SIGTERM):
                    previous[sig] = signal.signal(sig, cancel)
                return function(*args, **kwargs)
        except KeyboardInterrupt:
            return None
        except typer.Exit:
            # Click's Exit is also a RuntimeError; preserve configuration exit 2
            # so systemd does not restart an unconfigured receiver indefinitely.
            raise
        except RuntimeError as exc:
            typer.echo(f"Radio operation failed: {exc}", err=True)
            raise typer.Exit(3) from exc
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return run

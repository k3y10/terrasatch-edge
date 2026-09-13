"""Sequential analog target scan with bounded probes and activity holds."""

from dataclasses import replace
import threading

from .radio_calibration import probe_radio_noise
from .radio_receiver import ContinuousRtlReceiver
from .radio_targets import validate_rtl_target


class ScanningReceiver:
    def __init__(self, settings, targets, path_factory, on_rejection, *, dwell=2.0,
                 probe=probe_radio_noise, receiver_type=ContinuousRtlReceiver, on_state=None):
        if not 0.5 <= dwell <= 10:
            raise ValueError("Scan dwell must be between 0.5 and 10 seconds")
        if not targets or len(targets) > 100:
            raise ValueError("Scan requires 1-100 explicitly enabled targets")
        for target in targets:
            validate_rtl_target(target)
        self.settings, self.targets, self.path_factory = settings, targets, path_factory
        self.on_rejection, self.dwell = on_rejection, dwell
        self.probe, self.receiver_type, self.on_state = probe, receiver_type, on_state

    def captures(self, stop_event):
        while not stop_event.is_set():
            for target in self.targets:
                if stop_event.is_set():
                    return
                if self.on_state:
                    self.on_state("SCANNING", target)
                settings = replace(self.settings, channel=target.channel, target=target)
                sample = self.probe(settings, probe_seconds=self.dwell, stop_event=stop_event)
                if stop_event.is_set():
                    return
                if max(sample.levels, default=0) < settings.activity_rms_threshold:
                    continue
                if self.on_state:
                    self.on_state("MONITORING", target)
                # A child stop flag bounds activity hold and follows parent cancellation.
                hold_stop = threading.Event()
                done = threading.Event()
                def watch(done=done, hold_stop=hold_stop, settings=settings):
                    elapsed = 0.0
                    while not done.wait(0.05):
                        elapsed += 0.05
                        if stop_event.is_set() or elapsed >= settings.max_transmission_seconds:
                            hold_stop.set()
                            return
                watcher = threading.Thread(target=watch, daemon=True)
                watcher.start()
                captures = None
                try:
                    receiver = self.receiver_type(settings, capture_path_factory=self.path_factory,
                                                  on_rejection=self.on_rejection)
                    captures = receiver.captures(hold_stop)
                    yield from captures
                finally:
                    hold_stop.set()
                    try:
                        if captures is not None:
                            captures.close()
                    finally:
                        done.set()
                        watcher.join(timeout=1)

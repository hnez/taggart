from time import monotonic_ns


def trace(func):
    def wrap(obj, *args, **kwargs):
        trace_name = "::".join((func.__module__, obj.__class__.__name__, func.__name__))

        with obj._db.tracer.start(trace_name):
            return func(obj, *args, **kwargs)

    return wrap


class Trace:
    def __init__(self, tracer, name):
        self._tracer = tracer
        self.name = name
        self.start_time = monotonic_ns()

    def end(self):
        end_time = monotonic_ns()

        duration = end_time - self.start_time

        if self.name not in self._tracer.durations:
            self._tracer.durations[self.name] = 0

        if self.name not in self._tracer.calls:
            self._tracer.calls[self.name] = 0

        self._tracer.durations[self.name] += duration
        self._tracer.calls[self.name] += 1

    def __enter__(self):
        self.start_time = monotonic_ns()

    def __exit__(self, _exc_type, _exc, _traceback):
        self.end()


class Tracer:
    def __init__(self):
        self.durations = dict()
        self.calls = dict()

    def start(self, name):
        return Trace(self, name)

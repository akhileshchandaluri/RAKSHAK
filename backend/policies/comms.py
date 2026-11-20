"""Command channel between the central dispatcher and appliance controllers.

Each command is delivered after ``latency_s + U(0, jitter_s)`` or lost with
probability ``loss``. There are no acknowledgements; the central controller observes
the outcome only through measured frequency, which is the closed-loop setting of the hybrid study. For scale, 3GPP TR 45.820 (cellular IoT)
sets a 10 s design target for exception-report latency. Latency and loss here are
swept scenario parameters, not claims about a particular network.
"""

import heapq
import itertools

import numpy as np


class CommandChannel:
    def __init__(self, latency_s=0.0, jitter_s=0.0, loss=0.0, seed=0):
        self.latency_s, self.jitter_s, self.loss = latency_s, jitter_s, loss
        self.rng = np.random.default_rng(seed)
        self.queue = []
        self.counter = itertools.count()
        self.sent = self.lost = self.delivered = 0

    @property
    def ideal(self):
        return self.latency_s == 0 and self.jitter_s == 0 and self.loss == 0

    def send(self, now, payload):
        self.sent += 1
        if self.loss > 0 and self.rng.random() < self.loss:
            self.lost += 1
            return
        delay = self.latency_s + (self.rng.random() * self.jitter_s if self.jitter_s else 0.0)
        heapq.heappush(self.queue, (now + delay, next(self.counter), payload))

    def due(self, now):
        out = []
        while self.queue and self.queue[0][0] <= now + 1e-9:
            out.append(heapq.heappop(self.queue)[2])
        self.delivered += len(out)
        return out

    def heartbeat(self, n):
        """Which of n devices receive this tick's broadcast heartbeat."""
        if self.loss <= 0:
            return np.ones(n, dtype=bool)
        return self.rng.random(n) >= self.loss

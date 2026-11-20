"""Common interface for emergency dispatch policies.

Every policy shares the same AUFLS reference protection (``uses_ufls``), plant
model, inventory and seeds, so paired comparisons isolate the dispatch decision.
"""


class DispatchPolicy:
    name = "base"
    uses_ufls = True      # Reference AUFLS stages remain active underneath the policy.
    dispatches = False    # Whether ``dispatch`` is called every dispatch interval.

    def reset(self, fleet, cfg):
        """Called once after the fleet is built."""

    def on_step(self, fleet, now, frequency):
        """Called every plant step (50 ms) for local sensing and command delivery."""

    def dispatch(self, fleet, now, frequency, rocof, supply, available, load, allow_absorption):
        raise NotImplementedError


class NoControl(DispatchPolicy):
    """Experimental control: no AUFLS and no appliance dispatch."""
    name = "none"
    uses_ufls = False


class UFLSOnly(DispatchPolicy):
    """Reference AUFLS feeder-block shedding only."""
    name = "ufls"

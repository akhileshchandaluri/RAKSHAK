"""Policy registry. ``make_policy(name)`` returns a fresh policy instance."""

from policies.base import DispatchPolicy, NoControl, UFLSOnly


def make_policy(name, **options):
    if isinstance(name, DispatchPolicy):
        return name
    if name == "none":
        return NoControl()
    if name == "ufls":
        return UFLSOnly()
    if name in ("rakshak", "rakshak_unstaggered"):
        from policies.heuristic import HeuristicPolicy
        return HeuristicPolicy(staged=name == "rakshak")
    if name == "np_mrd":
        from policies.np_mrd import NadirPredictivePolicy
        return NadirPredictivePolicy(**options)
    if name == "hybrid":
        from policies.hybrid import HybridPolicy
        return HybridPolicy(**options)
    if name == "edge":
        from policies.edge import EdgePolicy
        return EdgePolicy()
    raise ValueError(f"Unknown policy {name!r}")

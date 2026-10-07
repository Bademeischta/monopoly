"""PropertyRL: rule-faithful property trading game simulator and RL research toolkit.

The top-level package intentionally imports nothing heavy so that the engine
sub-package stays free of third-party dependencies.
"""

from propertyrl.versions import ENGINE_VERSION, __version__

__all__ = ["ENGINE_VERSION", "__version__"]

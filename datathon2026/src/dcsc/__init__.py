"""Global Conflicts - Impact on Supply Chains (CDM Datathon 2026, Theme 6.2).

The package is organised as a straight pipeline:

``ingest`` -> ``features`` -> ``analysis`` -> ``viz`` / ``report`` / ``powerbi``

Every stage writes a tabular artefact to ``outputs/tables`` so that any single
number in the report or the Power BI model can be traced back to the row set it
came from.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["analysis", "config", "features", "ingest", "powerbi", "report", "viz"]

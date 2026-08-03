"""Standalone RF direction-finding tools for a synchronized 4-channel SDR array.

This package is independent of the atlas pipeline (``app``/``agents``/
``crawlers``): it processes live IQ capture buffers from hardware, not
crawled/curated platform records. It lives in this repository because the
tracking work started on the ``drone-sdr-tracker`` branch here; it does not
read from or write to the atlas database.
"""

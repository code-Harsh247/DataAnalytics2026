"""Virtual gateway: a stand-in for an inverter data logger.

Runs as its own process, separate from the website and the API. It holds a
device token (from pairing), simulates a plant's inverters from real weather
and the same physics as the backfill, and pushes telemetry to Supabase through
the `ingest_telemetry` function -- the same path a real logger would use.
See Contract 4/5 in PRODUCT_PLAN.md ("Working MVP").

    python -m gateway pair <CODE>     # once, with the code shown in the app
    python -m gateway run             # catch up, then stream live readings
"""

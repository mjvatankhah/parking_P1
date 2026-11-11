# Hourly dashboard scroll diagnosis — 2026-11-07

The hourly chart rebuilt its Matplotlib figure and uploaded a new raster on every
scroll position change, on Kivy's UI thread. A 700×280 chart with 24 hourly samples
blocked each pan for 427–542 ms in the local software-OpenGL environment.

The chart now rasterizes the full day when data, metric or size changes. Panning
selects a GPU texture region; separate margin images keep the vertical scale
stationary. The same ten-position harness measured 0.77–1.79 ms per pan after the
fix (including both the property callback and an explicit `_draw()` call).
This measures chart pan work, not whole-application frame rate or live camera load.
Initial/data-change rasterization still runs synchronously.

Regression: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_chart*.py'`
checks raster reuse, shared GPU texture, fixed margins, data invalidation and chart
semantics. Before the fix the new regression failed with four unexpected Agg draws.
`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p '*scroll.py'`
checks nested pointer scrolling and record-list anchors across refreshes.
Set KIVY_HOME and MPLCONFIGDIR to writable temporary directories when sandboxed.

# Round 3 targeted fixes

- Added shared read-model storage layer: `src/inspection_utils/inspection_utils/read_model_store.py`
- Externalized query-side trace refresh policy via `query_side_trace_refresh`
- Added WebSocket send timeout / slow-client handling
- Switched frontend package scripts to direct JS entry points under node_modules
- Added regression tests for disabled query refresh and websocket send timeout

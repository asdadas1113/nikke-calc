# NIKKE optimizer Fast Engine prototype

Separate prototype. It does not modify Moris.

- `fast_engine/inventory.py`: Moris DSL structural inventory/classification
- `fast_engine/ir.py`: lossless effect/trigger IR compiler
- `fast_engine/catalog.py`: catalog loader
- `fast_engine/routing.py`: explicit Fast/Moris capability router
- `tests/test_routing.py`: routing safety tests
- `PHASE1_REPORT.md`: feasibility findings and next runtime priorities

Run from this directory:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

By default the prototype resolves the Moris repository from the surrounding checkout. Set `MORIS_ROOT=/path/to/nikke-calc` to test against another checkout.

The current code is a feasibility/compiler/router prototype, not a damage runtime.

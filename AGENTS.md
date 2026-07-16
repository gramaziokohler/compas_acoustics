# AGENTS.md

## Cursor Cloud specific instructions

`compas_acoustics` is a single Python library (COMPAS ecosystem) for room-acoustics
simulation, analysis, and auralisation. There is no web server, database, or
long-running service — everything runs as Python scripts/tests from the terminal.

### Environment

- Dependencies are installed into a virtualenv at `.venv/` (gitignored). The update
  script creates it and runs `pip install -e ".[dev]"`.
- **Always activate the venv first**: `source .venv/bin/activate`. This is required
  for the `invoke` tasks in particular, because `invoke lint`/`invoke check` shell out
  to the `ruff` executable by name and it must be on `PATH` (running
  `.venv/bin/invoke` alone fails with `ruff: command not found`).
- The venv depends on the `python3.12-venv` system package. It is already present in
  the VM snapshot; it is intentionally not in the update script.

### Lint / test / build / run

Standard commands (see `tasks.py`, `pyproject.toml`, `CONTRIBUTING.md`). Run from repo
root with the venv activated:

- Lint: `invoke lint` (ruff) — or `invoke check` for code+doc style.
- Test: `pytest` (or `invoke test`). Test paths configured in `pyproject.toml`.
- Docs (optional): `invoke docs` (Sphinx → `docs/_build/`).

### Running the library end-to-end

- Set a headless matplotlib backend when running any example/script that plots
  (e.g. `MPLBACKEND=Agg`), since there is no display; otherwise `analyser.plot(...)`
  can block or error.
- Known caveat: `examples/demo.py` is stale — it indexes the simulation result as
  `rirs[1][1]`, but `Simulator.rir_from_ray_tracing()` / `rir_from_image_source_method()`
  now return a **dict** keyed by `f"{receiver.guid}_{source.guid}"` whose values are
  `ImpulseResponse` objects. To analyse a result, pass `impulse_response.ir` (a numpy
  array) to `AcousticAnalyser`. A minimal working flow:
  build a `Scene` (room + `Source` + `Receiver` + `AcousticMaterial`s) →
  `Simulator(scene, simulation_platform="pyroomacoustics").rir_from_ray_tracing(...)` →
  `AcousticAnalyser(next(iter(rirs.values())).ir).analyse()` → `print_table()`.
- The 3D viewer (`compas_viewer`) requires a GUI/display and is optional; skip it in
  headless runs.

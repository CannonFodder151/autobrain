"""Vehicle domain module.

A self-contained vertical slice of the backend, layered as
``models`` -> ``schemas`` -> ``services`` -> ``api``:

  - ``models/vehicle.py``   — ``Vehicle`` / ``VehicleEvent`` ORM models
  - ``schemas/vehicle.py``  — request/response Pydantic models
  - ``services/``           — ownership, odometer, rego, timeline logic
  - ``api/vehicles.py``     — the FastAPI ``/vehicles`` router

Deliberately empty of imports: eagerly importing the ``api`` layer here would
pull ``app.api.deps`` into the module graph and create a cycle, since
``app.models`` re-exports from ``app.modules.vehicles.models``. Import the
sub-layers directly instead. Layer boundaries are enforced by
``backend/.importlinter``.
"""
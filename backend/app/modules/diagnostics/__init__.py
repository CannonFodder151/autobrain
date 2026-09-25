"""Vehicle diagnostics module contract.

Actual implementations live in:
- app.services.ai_client (AI-powered diagnostics)
- app.services.odometer (odometer source priority)
"""

__all__ = [
    "run_diagnostics",
    "predict_service",
]


def __getattr__(name: str):
    if name in __all__:
        from app.services.ai_client import run_diagnostics, predict_service
        globals()["run_diagnostics"] = run_diagnostics
        globals()["predict_service"] = predict_service
        return globals()[name]
    raise AttributeError(f"module 'app.modules.diagnostics' has no attribute '{name}'")
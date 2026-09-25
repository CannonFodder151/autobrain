"""AutoBrain backend modules.

Domain modules encapsulate business logic with explicit interfaces.
Each module owns its API routes, service layer, models, and schemas.

Module structure:
    modules/
        auth/          - Authentication and authorization
        vehicles/      - Vehicle management
        fuel/          - Fuel tracking and analytics
        diagnostics/   - Vehicle diagnostics
        ai_client/     - AI gateway client
        social/        - Community garage
"""

__all__ = ["auth", "vehicles", "fuel", "diagnostics", "ai_client", "social"]

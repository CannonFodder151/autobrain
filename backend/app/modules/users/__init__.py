"""User domain module.

Owns accounts, authentication, devices and Home Assistant integration. Routes:
`app.api.v1.auth`, `app.api.v1.passkey`, `app.api.v1.devices`,
`app.api.v1.dongle_firmware`, `app.api.v1.ha`; services:
`app.services.auth`, `app.services.passkey`, `app.services.device_keys`;
models: `app.models.user`, `app.models.device`, `app.models.ha`.
"""

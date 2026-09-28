/// Result of a location request with typed failure reasons (AUT-4489).
sealed class LocationResult {
  const LocationResult();

  const factory LocationResult.success(double latitude, double longitude) =
      _Success;

  const factory LocationResult.serviceDisabled() = _ServiceDisabled;

  const factory LocationResult.permissionDenied() = _PermissionDenied;

  const factory LocationResult.permissionDeniedForever() = _PermissionDeniedForever;

  const factory LocationResult.timeout() = _Timeout;

  const factory LocationResult.unexpectedError() = _UnexpectedError;

  bool get isSuccess => this is _Success;

  Map<String, double>? get coordinates {
    if (this is _Success s) return {'latitude': s.latitude, 'longitude': s.longitude};
    return null;
  }

  /// User-friendly message for the failure reason.
  String? get errorMessage {
    switch (this) {
      case _ServiceDisabled():
        return 'Location services are turned off. Enable them in system settings.';
      case _PermissionDenied():
        return 'Allow location access for this app to find nearby stations.';
      case _PermissionDeniedForever():
        return 'Location access was permanently denied. Open app settings to re-enable.';
      case _Timeout():
        return 'Could not get a GPS fix in time. Try again or move outdoors.';
      case _UnexpectedError():
        return 'Could not determine location. Check your connection and try again.';
      case _Success():
        return null;
    }
  }

  /// Whether the user can fix this by opening app/system settings.
  bool get canOpenSettings => this is _PermissionDeniedForever;
}

class _Success extends LocationResult {
  final double latitude;
  final double longitude;
  const _Success(this.latitude, this.longitude);
}

class _ServiceDisabled extends LocationResult {
  const _ServiceDisabled();
}

class _PermissionDenied extends LocationResult {
  const _PermissionDenied();
}

class _PermissionDeniedForever extends LocationResult {
  const _PermissionDeniedForever();
}

class _Timeout extends LocationResult {
  const _Timeout();
}

class _UnexpectedError extends LocationResult {
  const _UnexpectedError();
}
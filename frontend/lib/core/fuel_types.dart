import 'api_client.dart';

/// Canonical fuel-type tokens, mirroring ``feeds.DEFAULT_FUEL_TYPES`` on the
/// backend (the union of types present in the price feeds). Used as the
/// fallback when ``GET /fuel/types`` is unavailable or premium-gated.
const List<String> defaultFuelTypes = [
  'E10',
  '91',
  '95',
  '98',
  'Diesel',
  'LPG',
];

/// Data-driven fuel-type options for the vehicle edit/add dropdowns.
///
/// Tries ``GET /api/fuel/types`` first; on any failure (network error,
/// premium gate, empty payload) it falls back to [defaultFuelTypes] so the
/// dropdown is always populated. Returns a distinct list safe to mutate.
Future<List<String>> fetchFuelTypes(ApiClient api) async {
  try {
    final resp = await api.get('/fuel/types');
    if (resp is List) {
      final fromApi = resp.whereType<String>().toList();
      if (fromApi.isNotEmpty) return List<String>.from(fromApi);
    }
  } catch (_) {
    // API unavailable or premium-gated — use the static list.
  }
  return List<String>.from(defaultFuelTypes);
}

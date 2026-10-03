/// Web GPS helper. On non-web platforms returns null.
library;

export 'location_result.dart';
export 'geoloc_io.dart' if (dart.library.html) 'geoloc_web.dart';
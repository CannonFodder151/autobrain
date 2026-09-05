/// Typed models mirroring the backend API schemas.
///
/// Per-domain model files live in `models/` and are wired in here with `part`
/// directives, so the single `library models` scope keeps all existing
/// `import 'package:autobrain/core/models.dart'` call sites unchanged.
library models;

part 'models/vehicle.dart';
part 'models/service.dart';
part 'models/fuel.dart';
part 'models/electricity.dart';
part 'models/diagnostic.dart';
part 'models/trip.dart';
part 'models/obd.dart';
part 'models/modification.dart';
part 'models/part.dart';
part 'models/receipt.dart';
part 'models/valuation.dart';
part 'models/analytics.dart';
part 'models/timeline.dart';

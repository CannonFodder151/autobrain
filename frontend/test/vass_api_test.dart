import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/models.dart';
import 'package:autobrain/services/vass_api.dart';

/// Minimal [ApiClient] double that records calls and returns canned JSON.
class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  final calls = <String>[];
  Object? response;
  Object? lastBody;
  Map<String, String>? lastQuery;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) {
    lastQuery = query;
    calls.add('GET $path');
    return Future.value(response);
  }

  @override
  Future<dynamic> post(String path, [Object? body, Map<String, String>? headers]) {
    calls.add('POST $path');
    lastBody = body;
    return Future.value(response);
  }

  @override
  Future<dynamic> patch(String path, [Object? body]) {
    calls.add('PATCH $path');
    lastBody = body;
    return Future.value(response);
  }

  @override
  Future<dynamic> delete(String path) {
    calls.add('DELETE $path');
    return Future.value(null);
  }
}

const _precheckJson = {
  'id': 'pc-1',
  'vehicle_id': 'veh-1',
  'user_id': 'usr-1',
  'jurisdiction': 'VIC',
  'status': 'completed',
  'vin': 'JTDBR32E160012345',
  'make': 'Toyota',
  'model': 'Corolla',
  'year': 2006,
  'body_type': 'sedan',
  'engine': '1ZZ-FE',
  'transmission': 'manual',
  'modifications': [
    {'name': 'Coilovers', 'category': 'suspension', 'brand': 'Bilstein'}
  ],
  'completed_at': '2026-09-20T10:00:00Z',
  'created_at': '2026-09-19T09:00:00Z',
  'updated_at': '2026-09-20T10:00:00Z',
};

void main() {
  group('VASS models', () {
    test('enums round-trip wire values and default safely', () {
      expect(VassJurisdiction.fromString('QLD'), VassJurisdiction.QLD);
      expect(VassJurisdiction.fromString('XX'), VassJurisdiction.VIC);
      expect(ComplianceStatus.fromString('conditional'),
          ComplianceStatus.conditional);
      expect(ComplianceStatus.fromString('bogus'), ComplianceStatus.pending);
      expect(PrecheckStatus.fromString('in_progress'),
          PrecheckStatus.inProgress);
      expect(EngineerType.fromString('inspector'), EngineerType.inspector);
      expect(EngineerType.fromString('nope'), EngineerType.signatory);
      expect(ComplianceStatus.na.value, 'na');
    });

    test('PrecheckOut.fromJson parses mods, timestamps and nullable fields', () {
      final p = PrecheckOut.fromJson(_precheckJson);
      expect(p.id, 'pc-1');
      expect(p.jurisdiction, VassJurisdiction.VIC);
      expect(p.status, PrecheckStatus.completed);
      expect(p.modifications.single.name, 'Coilovers');
      expect(p.modifications.single.brand, 'Bilstein');
      expect(p.completedAt, DateTime.utc(2026, 9, 20, 10));

      final sparse = PrecheckOut.fromJson({
        'id': 'pc-2',
        'vehicle_id': 'veh-2',
        'user_id': 'usr-2',
        'jurisdiction': 'NSW',
        'status': 'draft',
        'vin': null,
        'make': null,
        'model': null,
        'year': null,
        'body_type': null,
        'engine': null,
        'transmission': null,
        'modifications': [],
        'completed_at': null,
        'created_at': '2026-09-19T09:00:00Z',
        'updated_at': '2026-09-19T09:00:00Z',
      });
      expect(sparse.vin, isNull);
      expect(sparse.completedAt, isNull);
      expect(sparse.modifications, isEmpty);
    });

    test('PrecheckCreate.toJson omits unset optionals', () {
      final payload = PrecheckCreate(
        vehicleId: 'veh-1',
        make: 'Toyota',
        modifications: const [
          ModificationSelection(name: 'Exhaust', category: 'exhaust')
        ],
      ).toJson();
      expect(payload['vehicle_id'], 'veh-1');
      expect(payload['jurisdiction'], 'VIC');
      expect(payload.containsKey('vin'), isFalse);
      final mods = payload['modifications'] as List;
      expect((mods.first as Map)['name'], 'Exhaust');
      expect((mods.first as Map).containsKey('brand'), isFalse);
    });

    test('PrecheckUpdate.toJson only emits set fields', () {
      expect(
        PrecheckUpdate(status: PrecheckStatus.completed).toJson(),
        {'status': 'completed'},
      );
      expect(
        PrecheckUpdate(jurisdiction: VassJurisdiction.QLD).toJson(),
        {'jurisdiction': 'QLD'},
      );
      expect(PrecheckUpdate().toJson(), isEmpty);
    });

    test('EngineerOut.fromJson handles missing specialisations and rating', () {
      final e = EngineerOut.fromJson({
        'id': 'eng-1',
        'jurisdiction': 'WA',
        'engineer_type': 'consultant',
        'name': 'Jane Doe',
        'is_active': true,
        'review_count': 3,
        'created_at': '2026-09-01T00:00:00Z',
        'updated_at': '2026-09-01T00:00:00Z',
      });
      expect(e.specialisations, isEmpty);
      expect(e.rating, isNull);
      expect(e.licenseExpiry, isNull);
      expect(e.engineerType, EngineerType.consultant);
      expect(e.reviewCount, 3);
    });

    test('EngineerCreate.toJson formats license_expiry as ISO date', () {
      final json = EngineerCreate(
        jurisdiction: VassJurisdiction.VIC,
        name: 'John',
        licenseExpiry: DateTime(2027, 3, 4),
      ).toJson();
      expect(json['license_expiry'], '2027-03-04');
      expect(json['engineer_type'], 'signatory');
      expect(json['name'], 'John');
    });

    test('EngineerSearchParams.toQuery always carries paging', () {
      final q = const EngineerSearchParams(
        jurisdiction: VassJurisdiction.QLD,
        minRating: 4.5,
        page: 2,
        pageSize: 10,
      ).toQuery();
      expect(q['jurisdiction'], 'QLD');
      expect(q['min_rating'], '4.5');
      expect(q['page'], '2');
      expect(q['page_size'], '10');
      expect(q['is_active'], 'true');
      expect(q.containsKey('suburb'), isFalse);
    });

    test('ComplianceAggregationResponse.fromJson defaults counters', () {
      final a = ComplianceAggregationResponse.fromJson({
        'overall_score': 72.5,
        'total_mods': 3,
        'passed': 1,
        'failed': 0,
        'conditional': 1,
        'pending': 1,
        'requires_engineer_review': true,
        'summary': 'Needs review',
      });
      expect(a.overallScore, 72.5);
      expect(a.requiresEngineerReview, isTrue);
      expect(a.results, isEmpty);
    });

    test('VinValidationResponse.fromJson parses decoded fields', () {
      final v = VinValidationResponse.fromJson({
        'vin': 'JTDBR32E160012345',
        'is_valid': true,
        'errors': [],
        'check_digit_valid': false,
        'manufacturer': 'Toyota',
        'country': 'Japan',
        'year': 2006,
        'is_right_hand_drive': true,
      });
      expect(v.isValid, isTrue);
      expect(v.checkDigitValid, isFalse);
      expect(v.manufacturer, 'Toyota');
      expect(v.isRightHandDrive, isTrue);
    });

    test('ImportPathwayDetailOut inherits base fields and adds checklist', () {
      final d = ImportPathwayDetailOut.fromJson({
        'id': 'ip-1',
        'vin': 'JTDBR32E160012345',
        'jurisdiction': 'VIC',
        'pathway_type': 'raws',
        'eligibility': 'eligible',
        'adr_requirements': ['ADR 1-85'],
        'created_at': '2026-09-01T00:00:00Z',
        'updated_at': '2026-09-01T00:00:00Z',
        'document_checklist': [
          {'name': 'RAV listing confirmation'},
          {'name': 'ADR compliance certificate', 'required': false}
        ],
      });
      expect(d.pathwayType, 'raws');
      expect(d.adrRequirements, ['ADR 1-85']);
      expect(d.documentChecklist, hasLength(2));
      expect(d.documentChecklist.first.required, isTrue);
      expect(d.documentChecklist.last.required, isFalse);
    });
  });

  group('VassApi', () {
    test('listPrechecks omits the query when no vehicleId', () async {
      final api = _FakeApi()..response = [_precheckJson];
      final list = await VassApi(api).listPrechecks();
      expect(api.calls, ['GET /vass/prechecks']);
      expect(api.lastQuery, isNull);
      expect(list.single.id, 'pc-1');
    });

    test('listPrechecks sends vehicle_id filter', () async {
      final api = _FakeApi()..response = <Map<String, dynamic>>[];
      await VassApi(api).listPrechecks(vehicleId: 'veh-1');
      expect(api.lastQuery, {'vehicle_id': 'veh-1'});
    });

    test('createPrecheck POSTs the snake_case payload', () async {
      final api = _FakeApi()..response = _precheckJson;
      final created = await VassApi(api).createPrecheck(
        PrecheckCreate(vehicleId: 'veh-1', make: 'Toyota', year: 2006),
      );
      expect(api.calls, ['POST /vass/prechecks']);
      expect((api.lastBody as Map)['vehicle_id'], 'veh-1');
      expect((api.lastBody as Map)['year'], 2006);
      expect(created.status, PrecheckStatus.completed);
    });

    test('completePrecheck POSTs and returns the updated precheck', () async {
      final api = _FakeApi()..response = _precheckJson;
      final done = await VassApi(api).completePrecheck('pc-1');
      expect(api.calls, ['POST /vass/prechecks/pc-1/complete']);
      expect(done.status, PrecheckStatus.completed);
    });

    test('getComplianceResults maps the list response', () async {
      final api = _FakeApi()
        ..response = [
          {
            'id': 'cr-1',
            'precheck_id': 'pc-1',
            'modification_name': 'Coilovers',
            'category': 'suspension',
            'status': 'conditional',
            'adr_references': ['ADR 01/00', 'ADR 02/00'],
            'vsb_references': ['VSB 6 Section 5'],
            'vsb6_references': <String>[],
            'notes': 'Height must stay within 25mm.',
            'conditional_details': null,
            'created_at': '2026-09-20T10:00:00Z',
          }
        ];
      final results = await VassApi(api).getComplianceResults('pc-1');
      expect(api.calls, ['GET /vass/prechecks/pc-1/results']);
      expect(results.single.status, ComplianceStatus.conditional);
      expect(results.single.adrReferences, hasLength(2));
      expect(results.single.vsbReferences, ['VSB 6 Section 5']);
    });

    test('searchEngineers sends paging query by default', () async {
      final api = _FakeApi()
        ..response = {
          'engineers': <Map<String, dynamic>>[],
          'total': 0,
          'page': 1,
          'page_size': 20,
          'total_pages': 1,
        };
      final page = await VassApi(api).searchEngineers();
      expect(api.calls, ['GET /vass/engineers']);
      expect(api.lastQuery!['page'], '1');
      expect(api.lastQuery!['is_active'], 'true');
      expect(page.total, 0);
    });

    test('deletePrecheck DELETEs the precheck path', () async {
      final api = _FakeApi();
      await VassApi(api).deletePrecheck('pc-1');
      expect(api.calls, ['DELETE /vass/prechecks/pc-1']);
    });

    test('validateVin POSTs the bare VIN', () async {
      final api = _FakeApi()
        ..response = {
          'vin': 'JTDBR32E160012345',
          'is_valid': true,
          'errors': <String>[],
        };
      final v = await VassApi(api).validateVin('JTDBR32E160012345');
      expect(api.calls, ['POST /vass/vin/validate']);
      expect(api.lastBody, {'vin': 'JTDBR32E160012345'});
      expect(v.isValid, isTrue);
    });

    test('vehicleLookup POSTs make/model/year', () async {
      final api = _FakeApi()
        ..response = {
          'vehicles': [
            {
              'make': 'Toyota',
              'model': 'Corolla',
              'year_from': 1998,
              'year_to': 2007,
              'category': 'passenger',
              'rhd': true,
            }
          ],
          'total': 1,
          'make': 'Toyota',
          'model': 'Corolla',
          'year': 2006,
        };
      final res = await VassApi(api)
          .vehicleLookup(const VehicleLookupRequest(
              make: 'Toyota', model: 'Corolla', year: 2006));
      expect(api.calls, ['POST /vass/vehicle-lookup']);
      expect((api.lastBody as Map)['year'], 2006);
      expect(res.vehicles.single.rhd, isTrue);
      expect(res.total, 1);
    });
  });
}
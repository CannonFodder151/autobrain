// Regression test for AUT-676: the Community Garage share dialog must offer a
// Copy-link button and a way to open the build on the user's own instance;
// sharing a federated (remote) build must not throw a raw error.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/community_garage/community_garage_screen.dart';
import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';

class _FakeApi extends ApiClient {
  _FakeApi({this.remote = false}) : super(null);

  final bool remote;
  Map<String, dynamic> get _build => {
        'id': 'b1',
        'title': '2020 Honda CBR500R',
        'caption': 'My build',
        'author_display_name': 'Bob',
        'server_name': 'Server A',
        'origin': remote ? 'remote' : 'local',
        'snapshot': {'specs': {'make': 'Honda', 'model': 'CBR500R'}},
        'photos': const [],
        'like_count': 0,
        'comment_count': 0,
      };

  @override
  Future<dynamic> get(String path) async {
    if (path.startsWith('/social/feed')) return {'items': [_build]};
    if (path.startsWith('/social/share/')) return _build;
    if (path.startsWith('/social/posts/')) return _build;
    return {'items': const []};
  }

  @override
  Future<dynamic> post(String path, [Object? body]) async {
    if (path.endsWith('/share-link')) {
      return {'token': 'tok123', 'url': '/social/share/tok123'};
    }
    return _build;
  }
}

class _FakeAuthState extends AuthState {
  _FakeAuthState(this._api);
  final ApiClient _api;
  @override
  ApiClient get api => _api;
}

/// Captures what the app writes to the clipboard so the test can assert on it
/// (the platform channel has no clipboard in the test harness).
String? _copiedText;

void _mockClipboard(WidgetTester tester) {
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    SystemChannels.platform,
    (call) async {
      switch (call.method) {
        case 'Clipboard.setData':
          _copiedText = (call.arguments as Map)['text'] as String?;
          return null;
        case 'Clipboard.getData':
          return {'text': _copiedText};
        default:
          return null;
      }
    },
  );
}

Future<void> _pump(WidgetTester tester, _FakeApi api) async {
  _mockClipboard(tester);
  SharedPreferences.setMockInitialValues({});
  FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform({});
  await tester.pumpWidget(
    ChangeNotifierProvider<AuthState>(
      create: (_) => _FakeAuthState(api),
      child: const MaterialApp(home: CommunityGarageScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => TestWidgetsFlutterBinding.ensureInitialized());

  testWidgets('share dialog shows copy + view for a local build',
      (tester) async {
    await _pump(tester, _FakeApi());

    await tester.tap(find.byTooltip('Share link'));
    await tester.pumpAndSettle();

    expect(find.text('Share this build'), findsOneWidget);
    expect(find.text('Copy link'), findsOneWidget);
    expect(find.text('View'), findsOneWidget);

    await tester.tap(find.text('Copy link'));
    await tester.pumpAndSettle();

    expect(_copiedText, 'http://localhost:8000/social/share/tok123');
    expect(find.text('Link copied to clipboard'), findsOneWidget);
  });

  testWidgets('view button opens the build on the user own instance',
      (tester) async {
    await _pump(tester, _FakeApi());

    await tester.tap(find.byTooltip('Share link'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('View'));
    await tester.pumpAndSettle();

    // ShareLinkView resolves through the local API and replaces itself with
    // the post detail screen.
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('Honda CBR500R'), findsOneWidget);
  });

  testWidgets('sharing a federated build opens it without a raw error',
      (tester) async {
    await _pump(tester, _FakeApi(remote: true));

    await tester.tap(find.byTooltip('Share link'));
    await tester.pumpAndSettle();

    expect(find.text('View this build'), findsOneWidget);
    expect(find.text('View build'), findsOneWidget);
    expect(find.textContaining('another server'), findsOneWidget);

    await tester.tap(find.text('View build'));
    await tester.pumpAndSettle();

    expect(find.text('Honda CBR500R'), findsOneWidget);
  });
}

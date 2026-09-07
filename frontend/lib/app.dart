import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/connectivity_service.dart';
import 'core/config.dart';
import 'core/theme.dart';
import 'core/models.dart';
import 'widgets/stale_hint.dart';
import 'community_garage/screens/share_link_view.dart';
import 'screens/advisor/overview_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/reset_password.dart';
import 'screens/auth/server_setup_screen.dart';
import 'screens/auth/signup_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/settings/license_screen.dart';

class AutoBrainApp extends StatefulWidget {
  const AutoBrainApp({super.key});

  static String? initialFragment;

  static String? resetTokenFromUrl() {
    final uri = Uri.base;
    if (uri.pathSegments.isEmpty || uri.pathSegments.last != 'reset-password') return null;
    return _fragmentToken(uri.fragment) ?? uri.queryParameters['token'];
  }

  static String? _fragmentToken(String frag) {
    if (frag.isEmpty) return null;
    for (final part in frag.split('&')) {
      final kv = part.split('=');
      if (kv.length == 2 && kv[0] == 'token' && kv[1].isNotEmpty) {
        return Uri.decodeComponent(kv[1]);
      }
    }
    return null;
  }

  static String? shareTokenFromUrl() {
    final segs = Uri.base.pathSegments;
    if (segs.length >= 2 && segs.last == 's') {
      return Uri.base.queryParameters['token'] ?? segs[segs.length - 2];
    }
    if (segs.length >= 3 &&
        segs[segs.length - 3] == 'social' &&
        segs[segs.length - 2] == 'share') {
      return segs.last;
    }
    return null;
  }

  static bool signupRequested() {
    final uri = Uri.base;
    return uri.queryParameters['signup'] == '1' ||
        uri.pathSegments.contains('signup');
  }

  static bool licenseRequested() {
    final fragment =
        (initialFragment ?? Uri.base.fragment).replaceAll('/', '').toLowerCase();
    return fragment == 'license';
  }

  static int? advisorTabFromUrl() {
    final segs = Uri.base.pathSegments;
    if (segs.isEmpty || segs.first != 'advisor') return null;
    if (segs.length == 1) return 0;
    switch (segs[1]) {
      case 'value': return 1;
      case 'replace': return 2;
      case 'upgrade': return 3;
      case 'finance': return 4;
      case 'dream': return 5;
      case 'ai': return 6;
      default: return 0;
    }
  }

  @override
  State<AutoBrainApp> createState() => _AutoBrainAppState();
}

class _AutoBrainAppState extends State<AutoBrainApp> {
  @override
  void initState() {
    super.initState();
    ConnectivityService.instance.addListener(_rebuild);
  }

  @override
  void dispose() {
    ConnectivityService.instance.removeListener(_rebuild);
    super.dispose();
  }

  void _rebuild() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final resetToken = AutoBrainApp.resetTokenFromUrl();
    final shareToken = AutoBrainApp.shareTokenFromUrl();
    final advisorTab = AutoBrainApp.advisorTabFromUrl();

    Widget home;
    if (resetToken != null) {
      home = ResetPasswordScreen(token: resetToken);
    } else if (!AppConfig.serverConfigured) {
      home = const ServerSetupScreen();
    } else if (shareToken != null) {
      home = ShareLinkView(token: shareToken);
    } else if (auth.isLoggedIn) {
      if (AutoBrainApp.licenseRequested()) {
        home = const LicenseScreen();
      } else if (advisorTab != null) {
        home = _AdvisorDeepLink(tabIndex: advisorTab);
      } else {
        home = const HomeScreen();
      }
    } else if (AutoBrainApp.signupRequested() && auth.signupEnabled) {
      home = const SignupScreen();
    } else {
      home = const LoginScreen();
    }

    return MaterialApp(
      title: 'AutoBrain',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: auth.darkMode ? ThemeMode.dark : ThemeMode.light,
      home: home,
      builder: (context, child) {
        final content = child ?? const SizedBox.shrink();
        final banner = ConnectivityService.instance.isOnline
            ? null
            : MaterialBanner(
                content: Text(
                  'Offline — showing cached data',
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: Theme.of(context).colorScheme.onErrorContainer),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                elevation: 1,
                backgroundColor: Theme.of(context).colorScheme.errorContainer,
              );
        final body = banner == null
            ? content
            : Column(children: [banner, Expanded(child: content)]);
        final wrapped = MediaQuery.withClampedTextScaling(
          maxTextScale: 1.5,
          minTextScale: 1.0,
          child: body,
        );
        if (!(kDebugMode || kProfileMode)) {
          return wrapped;
        }
        final ok = AppConfig.lastValidationOk;
        final validation = ok == null
            ? 'not run'
            : ok
                ? 'ok'
                : 'fail';
        final apiHost = Uri.tryParse(AppConfig.apiBase)?.host ?? AppConfig.apiBase;
        return Stack(
          children: [
            wrapped,
            Positioned(
              left: 0,
              right: 0,
              top: 0,
              child: SafeArea(
                bottom: false,
                child: Container(
                  width: double.infinity,
                  color: Colors.black.withOpacity(0.55),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  child: Text(
                    'api: $apiHost  probe: $validation',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _AdvisorDeepLink extends StatefulWidget {
  const _AdvisorDeepLink({required this.tabIndex});
  final int tabIndex;

  @override
  State<_AdvisorDeepLink> createState() => _AdvisorDeepLinkState();
}

class _AdvisorDeepLinkState extends State<_AdvisorDeepLink> {
  Vehicle? _vehicle;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final auth = context.read<AuthState>();
    // Cache-first: render immediately from cache if available.
    final cached = await auth.api.getCachedDecoded('/vehicles', null);
    if (cached != null) {
      final data = cached as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _vehicle = Vehicle.resolveSelection(vehicles, null);
        _loading = false;
      });
    }
    // Background refresh if online.
    if (!ConnectivityService.instance.isOnline) return;
    try {
      final data = await auth.api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _vehicle = Vehicle.resolveSelection(vehicles, _vehicle);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (_vehicle == null) {
      return const HomeScreen();
    }
    return AdvisorOverviewScreen(
      vehicleId: _vehicle!.id,
      initialTabIndex: widget.tabIndex,
    );
  }
}

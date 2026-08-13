import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';
import '../../core/config.dart';
import '../../core/models.dart';
import '../../widgets/vehicle_selector.dart';
import '../admin/admin_screen.dart';
import '../analytics/analytics_screen.dart';
import '../diagnostics/diagnostics_screen.dart';
import '../fuel/fuel_screen.dart';
import '../logbook/logbook_screen.dart';
import '../mods/mods_screen.dart';
import '../notifications/notifications_screen.dart';
import '../obd/obd_screen.dart';
import '../parts/parts_screen.dart';
import '../receipts/receipts_screen.dart';
import '../services/service_list_screen.dart';
import '../settings/license_screen.dart';
import '../settings/settings_screen.dart';
import '../valuation/valuation_screen.dart';
import '../vehicles/vehicle_list_screen.dart';
import '../vehicles/vehicle_timeline_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Vehicle> _vehicles = const [];
  Vehicle? _selected;
  bool _loading = true;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final data = await api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      _vehicles = vehicles;
      _selected = Vehicle.resolveSelection(vehicles, _selected);
    } catch (_) {
      _loadError = 'Could not reach the server. Check your connection or server settings.';
    }
    setState(() => _loading = false);
  }

  void _showDownload() {
    showDialog<void>(
      context: context,
      builder: (_) => const DownloadAppDialog(),
    );
  }

  Future<void> _openDeleteAccount() async {
    final ok = await launchUrl(
      Uri.parse('https://autobrainservice.app/delete-account.html'),
      mode: LaunchMode.externalApplication,
    );
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the link.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            ClipOval(
              child: Image.asset('assets/logo.png',
                  width: 32, height: 32, fit: BoxFit.cover),
            ),
            const SizedBox(width: 10),
            const Text('AutoBrain'),
          ],
        ),
        actions: [
          IconButton(
            icon: Icon(auth.darkMode ? Icons.light_mode : Icons.dark_mode),
            tooltip: auth.darkMode ? 'Switch to light mode' : 'Switch to dark mode',
            onPressed: auth.toggleThemeMode,
          ),
          PopupMenuButton<String>(
            onSelected: (v) {
              switch (v) {
                case 'settings':
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const SettingsScreen()),
                  );
                case 'download':
                  _showDownload();
                case 'license':
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const LicenseScreen()),
                  );
                case 'admin':
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const AdminScreen()),
                  );
                case 'delete_account':
                  _openDeleteAccount();
                case 'logout':
                  auth.logout();
              }
            },
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'settings', child: Text('Settings & security')),
              if (!AppConfig.isMobile)
                const PopupMenuItem(value: 'download', child: Text('Get the mobile app')),
              if (auth.licenseEnabled)
                const PopupMenuItem(value: 'license', child: Text('License')),
              if (auth.isAdmin)
                const PopupMenuItem(value: 'admin', child: Text('User administration')),
              if (!auth.isAdmin && auth.licenseEnabled)
                const PopupMenuItem(value: 'delete_account', child: Text('Delete account')),
              const PopupMenuDivider(),
              const PopupMenuItem(value: 'logout', child: Text('Sign out')),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _loadError != null
                ? _ErrorView(message: _loadError!, onRetry: _load)
                : ListView(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                    children: [
                      if (_selected != null) _HeroCard(vehicle: _selected!),
                      const SizedBox(height: 12),
                      VehicleSelector(
                    vehicles: _vehicles,
                    selected: _selected,
                    onChanged: (v) => setState(() => _selected = v),
                    onManage: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => const VehicleListScreen(),
                        ),
                      );
                      _load();
                    },
                  ),
                  if (_selected == null)
                    const Padding(
                      padding: EdgeInsets.only(top: 40),
                      child: Center(
                        child: Text('Add a vehicle to get started.',
                            style: TextStyle(color: Colors.grey)),
                      ),
                    ),
                  if (_selected != null) ...[
                    const SizedBox(height: 20),
                    Text('Features',
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700)),
                    const SizedBox(height: 10),
                    _FeatureGrid(vehicle: _selected!),
                  ],
                ],
              ),
      ),
    );
  }
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({required this.vehicle});
  final Vehicle vehicle;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [scheme.primary, scheme.primary.withValues(alpha: 0.7), scheme.secondary],
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(vehicle.nickname,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w800)),
                const SizedBox(height: 2),
                Text(
                  '${vehicle.make ?? ''} ${vehicle.model ?? ''}'
                  '${vehicle.bodyType != null ? ' · ${vehicle.bodyType}' : ''}'
                  '${vehicle.colour != null ? ' · ${vehicle.colour}' : ''}'
                  '${vehicle.year != null ? ' · ${vehicle.year}' : ''}'
                  '${vehicle.isShared ? ' · Invited by ${vehicle.sharedBy ?? 'Unknown'}' : ''}'
                  .trim(),
                  style: const TextStyle(color: Colors.white70),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    _HeroStat(
                        icon: Icons.speed,
                        label: 'Odometer',
                        value: '${vehicle.odometerKm ?? 0} km'),
                    const SizedBox(width: 20),
                    _HeroStat(
                        icon: Icons.confirmation_number_outlined,
                        label: 'Rego',
                        value: vehicle.rego ?? '—'),
                  ],
                ),
              ],
            ),
          ),
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.18),
              shape: BoxShape.circle,
            ),
            child: Icon(
              vehicle.vehicleType == 'motorcycle'
                  ? Icons.two_wheeler
                  : Icons.directions_car,
              size: 40,
              color: Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroStat extends StatelessWidget {
  const _HeroStat({required this.icon, required this.label, required this.value});
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          Icon(icon, size: 18, color: Colors.white),
          const SizedBox(width: 6),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700)),
              Text(label, style: const TextStyle(color: Colors.white60, fontSize: 11)),
            ],
          ),
        ],
      );
}

class _FeatureGrid extends StatelessWidget {
  const _FeatureGrid({required this.vehicle});
  final Vehicle vehicle;

  @override
  Widget build(BuildContext context) {
    final items = [
      _Feature('Timeline', Icons.timeline, const Color(0xFF0B6B6A),
          VehicleTimelineScreen(vehicleId: vehicle.id)),
      _Feature('Services', Icons.build, const Color(0xFF2563EB),
          ServiceListScreen(vehicleId: vehicle.id)),
      _Feature('Fuel', Icons.local_gas_station, const Color(0xFF16A34A),
          FuelScreen(vehicleId: vehicle.id)),
      if (!vehicle.clubReg)
        _Feature('Logbook', Icons.book, const Color(0xFF0D9488),
            LogbookScreen(vehicleId: vehicle.id)),
      _Feature('Diagnostics', Icons.medical_services, const Color(0xFFEA580C),
          DiagnosticsScreen(vehicleId: vehicle.id)),
      _Feature('Mods', Icons.tune, const Color(0xFF7C3AED),
          ModsScreen(vehicleId: vehicle.id)),
      _Feature('Receipts', Icons.receipt_long, const Color(0xFFDB2777),
          ReceiptsScreen(vehicleId: vehicle.id)),
      _Feature('Parts', Icons.inventory_2, const Color(0xFF0891B2),
          PartsScreen(vehicleId: vehicle.id)),
      _Feature('Valuation', Icons.sell, const Color(0xFF059669),
          ValuationScreen(vehicleId: vehicle.id)),
      _Feature('Analytics', Icons.insights, const Color(0xFFCA8A04),
          AnalyticsScreen(vehicleId: vehicle.id)),
      _Feature('Notifications', Icons.notifications_active,
          const Color(0xFF0E7490), NotificationsScreen(vehicleId: vehicle.id)),
      if (!kIsWeb)
        _Feature('OBD', Icons.settings_input_component, const Color(0xFF334155),
            ObdScreen(vehicleId: vehicle.id)),
    ];
    return GridView.count(
      crossAxisCount: 3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 0.92,
      children: [
        for (final f in items)
          _FeatureTile(feature: f),
      ],
    );
  }
}

class _FeatureTile extends StatelessWidget {
  const _FeatureTile({required this.feature});
  final _Feature feature;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => feature.screen),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                color: feature.color.withValues(alpha: 0.14),
                shape: BoxShape.circle,
              ),
              child: Icon(feature.icon, color: feature.color, size: 24),
            ),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Text(feature.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.w600)),
            ),
          ],
        ),
      ),
    );
  }
}

class _Feature {
  const _Feature(this.label, this.icon, this.color, this.screen);
  final String label;
  final IconData icon;
  final Color color;
  final Widget screen;
}

/// Offers the downloadable iOS/Android apps to a logged-in user.
class DownloadAppDialog extends StatelessWidget {
  const DownloadAppDialog({super.key});

  static const _androidUrl = 'https://play.google.com/store/apps/details?id=com.autobrainservice.app';
  static const _iosUrl = 'https://apps.apple.com/app/autobrain';

  Future<void> _open(BuildContext context, String url) async {
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the link.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('Get the AutoBrain app'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Install AutoBrain on your phone for the full experience — offline cache, '
            'push notifications and faster access.',
            style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14),
          ),
          const SizedBox(height: 18),
          FilledButton.tonalIcon(
            onPressed: () => _open(context, _androidUrl),
            icon: const Icon(Icons.android),
            label: const Text('Get it on Google Play'),
          ),
          const SizedBox(height: 10),
          FilledButton.tonalIcon(
            onPressed: () => _open(context, _iosUrl),
            icon: const Icon(Icons.apple),
            label: const Text('Get on the App Store'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: 56, color: scheme.error),
            const SizedBox(height: 16),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.tonalIcon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

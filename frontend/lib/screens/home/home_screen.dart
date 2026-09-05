import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/models.dart';
import '../../widgets/responsive.dart';
import '../../widgets/vehicle_selector.dart';
import '../../widgets/rego_status_badge.dart';
import '../../widgets/stale_hint.dart';
import '../admin/admin_screen.dart';
import '../analytics/analytics_screen.dart';
import '../../community_garage/community_garage_screen.dart';
import '../diagnostics/diagnostics_screen.dart';
import '../electricity/electricity_screen.dart';
import '../electric_spy/electric_spy_screen.dart';
import '../fuel/fuel_screen.dart';
import '../fuel/petrol_price_map_screen.dart';
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
import '../servo_spy/servo_spy_screen.dart';
import '../advisor/overview_screen.dart';
import '../advisor/car_check_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Vehicle> _vehicles = const [];
  Vehicle? _selected;
  bool _loading = true;
  bool _stale = false;
  String? _loadError;
  bool _sessionExpired = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    // Cache-first: render immediately from cache if available.
    final cached = await api.getCachedDecoded('/vehicles', null);
    if (cached != null) {
      final data = cached as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      if (mounted) {
        setState(() {
          _vehicles = vehicles;
          _selected = Vehicle.resolveSelection(vehicles, _selected);
          _loading = false;
          _stale = true;
        });
      }
    }
    // Background refresh if online.
    if (!ConnectivityService.instance.isOnline) {
      if (mounted && _loading) setState(() => _loading = false);
      return;
    }
    setState(() {
      _loadError = null;
      _sessionExpired = false;
    });
    try {
      final data = await api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _vehicles = vehicles;
        _selected = Vehicle.resolveSelection(vehicles, _selected);
        _loading = false;
        _stale = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.statusCode == 401) {
        _loadError = 'Your login has expired. Please log in again.';
        _sessionExpired = true;
      } else {
        _loadError = 'Could not reach the server. Check your connection or server settings.';
      }
      setState(() => _loading = false);
    } catch (_) {
      _loadError = 'Could not reach the server. Check your connection or server settings.';
      setState(() => _loading = false);
    }
  }

  void _showDownload() {
    if (!kIsWeb) return;
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
              if (kIsWeb)
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
                ? _ErrorView(
                    message: _loadError!,
                    sessionExpired: _sessionExpired,
                    onLogout: () => context.read<AuthState>().logout(),
                    onRetry: _load,
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                    children: [
                      if (_selected != null)
                        Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 600),
                            child: _HeroCard(vehicle: _selected!),
                          ),
                        ),
                      const SizedBox(height: 12),
                      Center(
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 600),
                          child: VehicleSelector(
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
                        ),
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
                        Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 600),
                            child: _OwnershipAdvisorLaunchCard(
                                vehicle: _selected!),
                          ),
                        ),
                        const SizedBox(height: 20),
                        Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 600),
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: Text('Features',
                                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                      fontWeight: FontWeight.w700)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 600),
                            child: _FeatureGrid(vehicle: _selected!),
                          ),
                        ),
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
          colors: [scheme.primary, scheme.primary.withOpacity(0.7), scheme.secondary],
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
                if (vehicle.hasRegoData) ...[
                  const SizedBox(height: 10),
                  RegoStatusBadge(
                    vehicle: vehicle,
                    premium: context.watch<AuthState>().premium,
                    dense: true,
                  ),
                ],
              ],
            ),
          ),
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.18),
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
    final isDesktop = context.isDesktop;
    final isElectric = PowertrainType.isElectric(vehicle.powertrain);
    final items = [
      _Feature('Timeline', Icons.timeline, const Color(0xFF0B6B6A),
          VehicleTimelineScreen(vehicleId: vehicle.id)),
      _Feature('Services', Icons.build, const Color(0xFF2563EB),
          ServiceListScreen(vehicleId: vehicle.id)),
      if (!isElectric)
        _Feature('Fuel', Icons.local_gas_station, const Color(0xFF16A34A),
            FuelScreen(vehicleId: vehicle.id)),
      if (!vehicle.clubReg)
        _Feature('Logbook', Icons.book, const Color(0xFF0D9488),
            LogbookScreen(vehicleId: vehicle.id)),
      _Feature('Diagnostics', Icons.medical_services, const Color(0xFFEA580C),
          DiagnosticsScreen(vehicleId: vehicle.id)),
      _Feature('Petrol Prices', Icons.map, Color(0xFF0E7490),
          PetrolPriceMapScreen()),
      _Feature('Mods', Icons.tune, const Color(0xFF7C3AED),
          ModsScreen(vehicleId: vehicle.id)),
      _Feature('Receipts', Icons.receipt_long, const Color(0xFFDB2777),
          ReceiptsScreen(vehicleId: vehicle.id)),
      _Feature('Parts', Icons.inventory_2, const Color(0xFF0891B2),
          PartsScreen(vehicle: vehicle)),
      _Feature('Valuation', Icons.sell, const Color(0xFF059669),
          ValuationScreen(vehicleId: vehicle.id)),
      const _Feature('Car Check', Icons.fact_check, Color(0xFF7C3AED),
          CarCheckScreen()),
      _Feature('Analytics', Icons.insights, const Color(0xFFCA8A04),
          AnalyticsScreen(vehicleId: vehicle.id)),
      _Feature('Notifications', Icons.notifications_active,
          const Color(0xFF0E7490), NotificationsScreen(vehicleId: vehicle.id)),
      if (!kIsWeb)
        _Feature('OBD', Icons.settings_input_component, const Color(0xFF334155),
            ObdScreen(vehicleId: vehicle.id)),
      _Feature('Ownership Advisor', Icons.insights,
          const Color(0xFF6366F1),
          _AdvisorEntry(vehicle: vehicle)),
      _Feature('Servo Spy', Icons.local_gas_station, Color(0xFFF59E0B),
          ServoSpyScreen()),
      if (isElectric) ...[
        _Feature('Electric Spy', Icons.ev_station, Color(0xFF0EA5E9),
            ElectricSpyScreen()),
        _Feature('Electricity', Icons.bolt, Color(0xFFCA8A04),
            ElectricityScreen(vehicleId: vehicle.id)),
      ],
      _Feature('Community Garage', Icons.groups, Color(0xFF0D9488),
          CommunityGarageScreen()),
    ];
    final width = MediaQuery.of(context).size.width;
    final cols = isDesktop
        ? (width > 1400 ? 4 : 3)
        : 2;
    return GridView.count(
      crossAxisCount: cols,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: isDesktop ? 1.1 : 0.92,
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
                color: feature.color.withOpacity(0.14),
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

/// Bridges the home grid to the Ownership Advisor entry point. The overview
/// screen needs the live vehicleId, which the grid already filters for on
/// `_Feature`s that need a vehicle; this indirection unpacks the id.
class _AdvisorEntry extends StatelessWidget {
  const _AdvisorEntry({required this.vehicle});
  final Vehicle vehicle;

  @override
  Widget build(BuildContext context) =>
      AdvisorOverviewScreen(vehicleId: vehicle.id);
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({
    required this.message,
    required this.sessionExpired,
    required this.onLogout,
    required this.onRetry,
  });
  final String message;
  final bool sessionExpired;
  final VoidCallback onLogout;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: scheme.error),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
            if (sessionExpired)
              TextButton(onPressed: onLogout, child: const Text('Log in again')),
          ],
        ),
      ),
    );
  }
}

class _OwnershipAdvisorLaunchCard extends StatelessWidget {
  const _OwnershipAdvisorLaunchCard({required this.vehicle});
  final Vehicle vehicle;

  static const _modules = <_ModuleChipData>[
    _ModuleChipData('Value', Icons.sell, Color(0xFF059669)),
    _ModuleChipData('Replace', Icons.swap_horiz, Color(0xFF2563EB)),
    _ModuleChipData('Upgrade', Icons.upgrade, Color(0xFF7C3AED)),
    _ModuleChipData('Finance', Icons.calculate, Color(0xFF0B6B6A)),
    _ModuleChipData('Dream', Icons.star, Color(0xFFDB2777)),
    _ModuleChipData('AI', Icons.psychology, Color(0xFF0891B2)),
  ];

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFF6366F1),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => AdvisorOverviewScreen(vehicleId: vehicle.id),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: const BoxDecoration(
                      color: Color(0x2FFFFFFF),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.insights,
                        color: Colors.white, size: 24),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Ownership Advisor',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Text(
                          'Live now',
                          style: TextStyle(
                            color: Color(0xFFE0E7FF),
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.4,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.arrow_forward,
                      color: Colors.white, size: 20),
                ],
              ),
              const SizedBox(height: 12),
              const Text(
                'What should you do with your car? Value, replace, upgrade, '
                'finance, dream — six answers, one screen. Deterministic '
                'where possible, AI only for the final call.',
                style: TextStyle(color: Colors.white, fontSize: 13, height: 1.35),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final m in _modules) _ModuleChip(data: m),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModuleChipData {
  const _ModuleChipData(this.label, this.icon, this.color);
  final String label;
  final IconData icon;
  final Color color;
}

class _ModuleChip extends StatelessWidget {
  const _ModuleChip({required this.data});
  final _ModuleChipData data;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.18),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(data.icon, color: Colors.white, size: 14),
          const SizedBox(width: 6),
          Text(
            data.label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class DownloadAppDialog extends StatelessWidget {
  const DownloadAppDialog({super.key});

  @override
  Widget build(BuildContext context) => AlertDialog(
        icon: const Icon(Icons.smartphone),
        title: const Text('Get the mobile app'),
        content: const Text(
          'AutoBrain is available as a native app for Android and iOS. '
          'Open this page on your phone to download it.',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close')),
        ],
      );
}

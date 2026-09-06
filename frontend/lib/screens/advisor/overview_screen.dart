import 'package:flutter/material.dart';

import 'value_screen.dart';
import 'replace_screen.dart';
import 'upgrade_screen.dart';
import 'finance_screen.dart';
import 'dream_screen.dart';
import 'ai_screen.dart';

class AdvisorOverviewScreen extends StatefulWidget {
  const AdvisorOverviewScreen({
    super.key,
    required this.vehicleId,
    this.initialTabIndex,
  });

  final String vehicleId;
  final int? initialTabIndex;

  @override
  State<AdvisorOverviewScreen> createState() =>
      _AdvisorOverviewScreenState();
}

class _AdvisorOverviewScreenState extends State<AdvisorOverviewScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 7, vsync: this);
    if (widget.initialTabIndex != null &&
        widget.initialTabIndex! >= 0 &&
        widget.initialTabIndex! < 7) {
      _tabController.index = widget.initialTabIndex!;
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ownership Advisor'),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Overview'),
            Tab(text: 'Value'),
            Tab(text: 'Replace'),
            Tab(text: 'Upgrade'),
            Tab(text: 'Finance'),
            Tab(text: 'Dream'),
            Tab(text: 'AI'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _OverviewTab(
            vehicleId: widget.vehicleId,
            onNavigate: (i) => _tabController.animateTo(i),
          ),
          AdvisorValueScreen(vehicleId: widget.vehicleId),
          AdvisorReplaceScreen(vehicleId: widget.vehicleId),
          AdvisorUpgradeScreen(vehicleId: widget.vehicleId),
          AdvisorFinanceScreen(vehicleId: widget.vehicleId),
          AdvisorDreamScreen(vehicleId: widget.vehicleId),
          AdvisorAiScreen(vehicleId: widget.vehicleId),
        ],
      ),
    );
  }
}

class _OverviewTab extends StatelessWidget {
  const _OverviewTab({
    required this.vehicleId,
    required this.onNavigate,
  });

  final String vehicleId;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Your Ownership Advisor covers six modules.',
            style: theme.textTheme.bodyMedium),
        const SizedBox(height: 16),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            _ModuleChip(
              icon: Icons.sell,
              label: 'Value',
              color: const Color(0xFF059669),
              tabIndex: 1,
              onNavigate: onNavigate,
            ),
            _ModuleChip(
              icon: Icons.swap_horiz,
              label: 'Replace',
              color: const Color(0xFF2563EB),
              tabIndex: 2,
              onNavigate: onNavigate,
            ),
            _ModuleChip(
              icon: Icons.upgrade,
              label: 'Upgrade',
              color: const Color(0xFF7C3AED),
              tabIndex: 3,
              onNavigate: onNavigate,
            ),
            _ModuleChip(
              icon: Icons.calculate,
              label: 'Finance',
              color: const Color(0xFF0B6B6A),
              tabIndex: 4,
              onNavigate: onNavigate,
            ),
            _ModuleChip(
              icon: Icons.star,
              label: 'Dream',
              color: const Color(0xFFDB2777),
              tabIndex: 5,
              onNavigate: onNavigate,
            ),
            _ModuleChip(
              icon: Icons.psychology,
              label: 'AI',
              color: const Color(0xFF0891B2),
              tabIndex: 6,
              onNavigate: onNavigate,
            ),
          ],
        ),
      ],
    );
  }
}

class _ModuleChip extends StatelessWidget {
  const _ModuleChip({
    required this.icon,
    required this.label,
    required this.color,
    required this.tabIndex,
    required this.onNavigate,
  });

  final IconData icon;
  final String label;
  final Color color;
  final int tabIndex;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      avatar: Icon(icon, color: color, size: 18),
      label: Text(label),
      onPressed: () => onNavigate(tabIndex),
    );
  }
}

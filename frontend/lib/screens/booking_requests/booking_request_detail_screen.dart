import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../widgets/responsive.dart';

/// Owner views full detail of a booking request.
class BookingRequestDetailScreen extends StatefulWidget {
  const BookingRequestDetailScreen({super.key, required this.requestId});
  final String requestId;

  @override
  State<BookingRequestDetailScreen> createState() => _BookingRequestDetailScreenState();
}

class _BookingRequestDetailScreenState extends State<BookingRequestDetailScreen> {
  BookingRequestDetail? _detail;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    try {
      final data = await api.get('/engineers/requests/${widget.requestId}') as Map<String, dynamic>;
      _detail = BookingRequestDetail.fromJson(data);
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'pending':
        return const Color(0xFFF59E0B);
      case 'accepted':
        return const Color(0xFF22C55E);
      case 'rejected':
        return const Color(0xFFEF4444);
      case 'completed':
        return const Color(0xFF3B82F6);
      case 'cancelled':
        return Colors.grey;
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final d = _detail;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Booking Request'),
        actions: [
          if (_detail?.status == 'pending')
            IconButton(
              icon: const Icon(Icons.cancel_outlined),
              tooltip: 'Cancel request',
              onPressed: _cancelRequest,
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : d == null
              ? _errorState(theme)
              : _buildDetail(theme, d),
    );
  }

  Widget _errorState(ThemeData theme) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 64, color: theme.colorScheme.error),
          const SizedBox(height: 16),
          Text('Failed to load booking request', style: theme.textTheme.titleMedium),
        ],
      ),
    );
  }

  Widget _buildDetail(ThemeData theme, BookingRequestDetail d) {
    final isDesktop = context.isDesktop;
    final vehicle = '${d.vehicleMake ?? ''} ${d.vehicleModel ?? ''}'.trim();
    final vehicleDisplay = '${d.vehicleNickname ?? vehicle} ${d.vehicleYear != null ? '(${d.vehicleYear})' : ''}'
        '${d.vehicleRego != null ? ' — ${d.vehicleRego}' : ''}';

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: EdgeInsets.all(isDesktop ? 24 : 16),
        children: [
          // Header card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              d.engineerName ?? 'Unknown Engineer',
                              style: theme.textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              vehicleDisplay,
                              style: theme.textTheme.bodyMedium?.copyWith(
                                color: theme.colorScheme.onSurface.withOpacity(0.7),
                              ),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: _statusColor(d.status).withOpacity(0.15),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Text(
                          d.statusLabel,
                          style: theme.textTheme.titleSmall?.copyWith(
                            color: _statusColor(d.status),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (d.engineerRating != null) ...[
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Icon(Icons.star, size: 16, color: Colors.amber),
                        const SizedBox(width: 4),
                        Text('${d.engineerRating!.toStringAsFixed(1)} rating'),
                        if (d.engineerPhone != null) ...[
                          const SizedBox(width: 16),
                          const Icon(Icons.phone, size: 16),
                          const SizedBox(width: 4),
                          Text(d.engineerPhone!),
                        ],
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Service details
          _buildSection(theme, 'Service Details', [
            _detailRow('Service Type', d.serviceType),
            if (d.description != null && d.description!.isNotEmpty)
              _detailRow('Description', d.description!),
            _detailRow('Urgency', d.urgencyLabel),
            if (d.preferredDate != null)
              _detailRow('Preferred Date', d.preferredDate!),
            if (d.preferredTime != null)
              _detailRow('Preferred Time', d.preferredTime!),
          ]),

          // Engineer response
          if (d.status != 'pending') ...[
            const SizedBox(height: 16),
            _buildSection(theme, 'Engineer Response', [
              if (d.engineerNotes != null && d.engineerNotes!.isNotEmpty)
                _detailRow('Notes', d.engineerNotes!),
              if (d.quotedPrice != null)
                _detailRow('Quoted Price', '\$${d.quotedPrice!.toStringAsFixed(2)}'),
              if (d.scheduledDate != null)
                _detailRow('Scheduled Date', d.scheduledDate!),
              if (d.scheduledTime != null)
                _detailRow('Scheduled Time', d.scheduledTime!),
              if (d.respondedAt != null)
                _detailRow('Responded', _formatDateTime(d.respondedAt!)),
            ]),
          ],

          // Pre-check report
          if (d.preCheckReport != null) ...[
            const SizedBox(height: 16),
            _buildPreCheckReport(theme, d.preCheckReport!),
          ],

          // Symptoms & Mods
          if (d.symptoms.isNotEmpty || d.mods.isNotEmpty || d.odometerKm != null) ...[
            const SizedBox(height: 16),
            _buildSection(theme, 'Vehicle Details', [
              if (d.odometerKm != null)
                _detailRow('Odometer', '${d.odometerKm!,} km'),
              if (d.symptoms.isNotEmpty)
                _detailRow('Symptoms', d.symptoms.join(', ')),
              if (d.mods.isNotEmpty)
                _detailRow('Modifications', d.mods.join(', ')),
            ]),
          ],

          // Timeline
          const SizedBox(height: 16),
          _buildSection(theme, 'Timeline', [
            if (d.createdAt != null)
              _detailRow('Submitted', _formatDateTime(d.createdAt!)),
            if (d.respondedAt != null)
              _detailRow('Engineer Responded', _formatDateTime(d.respondedAt!)),
            if (d.completedAt != null)
              _detailRow('Completed', _formatDateTime(d.completedAt!)),
          ]),
        ],
      ),
    );
  }

  Widget _buildSection(ThemeData theme, String title, List<Widget> children) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: TextStyle(
                fontWeight: FontWeight.w500,
                color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
              ),
            ),
          ),
          Expanded(
            child: Text(value),
          ),
        ],
      ),
    );
  }

  Widget _buildPreCheckReport(ThemeData theme, Map<String, dynamic> report) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Pre-Check Report',
              style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            if (report['vehicle'] != null) ...[
              Text('Vehicle: ${_formatVehicle(report['vehicle'])}'),
              const SizedBox(height: 8),
            ],
            if (report['checks'] != null && (report['checks'] as List).isNotEmpty) ...[
              Text('Checks:', style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              for (final check in (report['checks'] as List))
                _preCheckItem(theme, check),
              const SizedBox(height: 12),
            ],
            if (report['recommendations'] != null && (report['recommendations'] as List).isNotEmpty) ...[
              Text('Recommendations:', style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              for (final rec in (report['recommendations'] as List))
                _recommendationItem(theme, rec),
              const SizedBox(height: 12),
            ],
            if (report['warnings'] != null && (report['warnings'] as List).isNotEmpty) ...[
              Text('Warnings:', style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600, color: Colors.orange)),
              const SizedBox(height: 8),
              for (final warn in (report['warnings'] as List))
                _warningItem(theme, warn),
            ],
          ],
        ),
      ),
    );
  }

  String _formatVehicle(Map<String, dynamic> v) {
    final parts = <String>[];
    if (v['make'] != null) parts.add(v['make']);
    if (v['model'] != null) parts.add(v['model']);
    if (v['year'] != null) parts.add(v['year'].toString());
    if (v['engine'] != null) parts.add(v['engine']);
    if (v['odometer_km'] != null) parts.add('${v['odometer_km']} km');
    return parts.join(' • ');
  }

  Widget _preCheckItem(ThemeData theme, dynamic check) {
    if (check is! Map) return const SizedBox.shrink();
    final item = check['item'] ?? '';
    final status = check['status'] ?? '';
    final detail = check['detail'] ?? '';
    Color statusColor;
    switch (status) {
      case 'due':
        statusColor = Colors.red;
        break;
      case 'inspect':
        statusColor = Colors.orange;
        break;
      case 'verify':
        statusColor = Colors.blue;
        break;
      case 'review':
        statusColor = Colors.amber;
        break;
      default:
        statusColor = Colors.green;
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 8,
            height: 8,
            margin: const EdgeInsets.only(top: 6, right: 8),
            decoration: BoxDecoration(color: statusColor, shape: BoxShape.circle),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500)),
                if (detail.isNotEmpty)
                  Text(detail, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurface.withOpacity(0.6))),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _recommendationItem(ThemeData theme, String rec) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.lightbulb_outline, size: 16, color: Color(0xFF22C55E)),
          const SizedBox(width: 8),
          Expanded(child: Text(rec, style: theme.textTheme.bodyMedium)),
        ],
      ),
    );
  }

  Widget _warningItem(ThemeData theme, String warn) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber_rounded, size: 16, color: Colors.orange),
          const SizedBox(width: 8),
          Expanded(child: Text(warn, style: theme.textTheme.bodyMedium?.copyWith(color: Colors.orange[800]))),
        ],
      ),
    );
  }

  String _formatDateTime(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      return '${dt.day}/${dt.month}/${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }

  Future<void> _cancelRequest() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cancel booking request?'),
        content: const Text('This action cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Cancel')),
        ],
      ),
    );
    if (confirm != true) return;

    final api = context.read<AuthState>().api;
    try {
      await api.patch('/engineers/requests/${widget.requestId}/cancel', {});
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Booking request cancelled')),
        );
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to cancel: $e')),
        );
      }
    }
  }
}
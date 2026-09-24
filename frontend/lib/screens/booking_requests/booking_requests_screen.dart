import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/models.dart';
import '../../widgets/responsive.dart';
import 'booking_request_detail_screen.dart';
import 'booking_request_form_screen.dart';

/// List of booking requests submitted by the current user.
class BookingRequestsScreen extends StatefulWidget {
  const BookingRequestsScreen({super.key, this.vehicleId});
  final String? vehicleId;

  @override
  State<BookingRequestsScreen> createState() => _BookingRequestsScreenState();
}

class _BookingRequestsScreenState extends State<BookingRequestsScreen> {
  List<BookingRequestSummary> _requests = [];
  bool _loading = true;
  bool _stale = false;
  String? _filter;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    final path = widget.vehicleId != null
        ? '/vehicles/${widget.vehicleId}/engineers/requests'
        : '/engineers/requests';
    try {
      final data = await api.get(path) as List;
      _requests = data
          .map((e) => BookingRequestSummary.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = false;
    } catch (_) {
      _stale = _requests.isEmpty;
    }
    if (mounted) setState(() => _loading = false);
  }

  List<BookingRequestSummary> get _filtered {
    if (_filter == null) return _requests;
    return _requests.where((r) => r.status == _filter).toList();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDesktop = context.isDesktop;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Booking Requests'),
        actions: [
          if (_stale)
            const Padding(
              padding: EdgeInsets.only(right: 8),
              child: StaleHint(),
            ),
          IconButton(
            icon: const Icon(Icons.filter_list),
            onPressed: _showFilterSheet,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _requests.isEmpty
              ? _emptyState(theme)
              : _buildList(theme, isDesktop),
      floatingActionButton: FloatingActionButton(
        onPressed: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => const BookingRequestFormScreen(),
          ),
        ),
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _emptyState(ThemeData theme) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.engineering, size: 64, color: theme.colorScheme.primary.withOpacity(0.4)),
            const SizedBox(height: 16),
            Text(
              'No booking requests yet',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Find an engineer and submit a booking request for your vehicle.',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurface.withOpacity(0.6)),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildList(ThemeData theme, bool isDesktop) {
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: EdgeInsets.all(isDesktop ? 24 : 16),
        itemCount: _filtered.length + (_filter != null ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          if (_filter != null && i == _filtered.length) {
            return TextButton(
              onPressed: () => setState(() => _filter = null),
              child: const Text('Clear filter'),
            );
          }
          return _RequestCard(
            request: _filtered[i],
            onTap: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => BookingRequestDetailScreen(requestId: _filtered[i].id),
                ),
              );
              _load(); // refresh on return
            },
          );
        },
      ),
    );
  }

  void _showFilterSheet() {
    showModalBottomSheet(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: const Text('All'),
              leading: Icon(
                Icons.all_inclusive,
                color: _filter == null ? Theme.of(context).colorScheme.primary : null,
              ),
              onTap: () {
                setState(() => _filter = null);
                Navigator.pop(context);
              },
            ),
            for (final status in ['pending', 'accepted', 'rejected', 'completed', 'cancelled'])
              ListTile(
                title: Text(status[0].toUpperCase() + status.substring(1)),
                leading: Icon(
                  status == 'pending'
                      ? Icons.schedule
                      : status == 'accepted'
                          ? Icons.check_circle_outline
                          : status == 'rejected'
                              ? Icons.cancel_outlined
                              : status == 'completed'
                                  ? Icons.check_circle
                                  : Icons.block,
                  color: _filter == status ? Theme.of(context).colorScheme.primary : null,
                ),
                onTap: () {
                  setState(() => _filter = status);
                  Navigator.pop(context);
                },
              ),
          ],
        ),
      ),
    );
  }
}

class _RequestCard extends StatelessWidget {
  const _RequestCard({required this.request, required this.onTap});
  final BookingRequestSummary request;
  final VoidCallback onTap;

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
    final vehicle = '${request.vehicleMake ?? ''} ${request.vehicleModel ?? ''}'.trim();

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
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
                          request.engineerName ?? 'Unknown Engineer',
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (vehicle.isNotEmpty)
                          Text(
                            vehicle,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurface.withOpacity(0.6),
                            ),
                          ),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: _statusColor(request.status).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      request.statusLabel,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: _statusColor(request.status),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(Icons.build, size: 14, color: theme.colorScheme.primary),
                  const SizedBox(width: 4),
                  Text(request.serviceType, style: theme.textTheme.bodySmall),
                  const SizedBox(width: 16),
                  if (request.preferredDate != null) ...[
                    Icon(Icons.calendar_today, size: 14, color: theme.colorScheme.primary),
                    const SizedBox(width: 4),
                    Text(request.preferredDate!, style: theme.textTheme.bodySmall),
                  ],
                  const Spacer(),
                  if (request.quotedPrice != null)
                    Text(
                      '\$${request.quotedPrice!.toStringAsFixed(0)}',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                ],
              ),
              if (request.engineerNotes != null && request.engineerNotes!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  request.engineerNotes!,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withOpacity(0.6),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
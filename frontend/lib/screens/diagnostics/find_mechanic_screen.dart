/// Find a Mechanic — search nearby mechanics via Shop API (AUT-3750).
///
/// Cache-first loading with stale hint, location-based search, distance/rating/services display,
/// selection confirmation, and job request creation. Offline-aware with error handling.

library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/geoloc.dart';
import '../../core/models.dart';
import '../../widgets/stale_hint.dart';

class FindMechanicScreen extends StatefulWidget {
  const FindMechanicScreen({super.key, required this.vehicleId});

  final String vehicleId;

  @override
  State<FindMechanicScreen> createState() => _FindMechanicScreenState();
}

class _FindMechanicScreenState extends State<FindMechanicScreen> {
  bool _loading = true;
  bool _stale = false;
  String? _error;
  Map<String, double>? _position;
  List<ShopMechanic> _mechanics = const [];

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    _position = await getCurrentPosition();
    if (_position == null) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Enable location to find nearby mechanics.';
      });
      return;
    }

    await _fetchMechanics();
  }

  Future<void> _fetchMechanics() async {
    if (_position == null) return;

    final api = context.read<AuthState>().api;
    final path = '/shop/mechanics/search';
    final query = <String, String>{
      'lat': _position!['latitude']!.toStringAsFixed(6),
      'lon': _position!['longitude']!.toStringAsFixed(6),
      'radius_km': '25',
      'limit': '50',
    };

    final cached = await api.getCachedDecoded(path, query);
    if (cached != null) {
      _mechanics = (cached as List)
          .map((e) => ShopMechanic.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = true;
      if (!mounted) return;
      setState(() => _loading = false);
    }

    if (!mounted) return;
    if (!ConnectivityService.instance.isOnline) return;

    try {
      final data = await api.get(path, query: query) as List;
      _mechanics = data
          .map((e) => ShopMechanic.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = false;
    } on ApiException catch (e) {
      if (!mounted) return;
      if (_mechanics.isEmpty) {
        _error = 'Could not reach the server (${e.statusCode}).';
      }
    } catch (_) {
      if (!mounted) return;
      if (_mechanics.isEmpty) {
        _error = 'Could not load mechanics. Check your connection.';
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createJobRequest(ShopMechanic mechanic) async {
    final api = context.read<AuthState>().api;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Request service from ${mechanic.name}?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (mechanic.address != null) ...[
              Text(mechanic.address!),
              const SizedBox(height: 8),
            ],
            if (mechanic.distanceKm != null) ...[
              Text('${mechanic.distanceKm!.toStringAsFixed(1)} km away'),
              const SizedBox(height: 8),
            ],
            if (mechanic.rating != null) ...[
              Row(
                children: [
                  const Icon(Icons.star, size: 16, color: Colors.amber),
                  const SizedBox(width: 4),
                  Text('${mechanic.rating!.toStringAsFixed(1)} '
                      '(${mechanic.reviewCount ?? 0} reviews)'),
                ],
              ),
              const SizedBox(height: 8),
            ],
            const Text(
              'This will create a job request. The mechanic will contact you to confirm.',
              style: TextStyle(fontSize: 13, color: Colors.grey),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Create request'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    setState(() => _loading = true);
    try {
      await api.post('/shop/mechanics/${mechanic.id}/request-job', {
        'vehicle_id': widget.vehicleId,
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Job request sent to ${mechanic.name}'),
          backgroundColor: Colors.green,
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to create request (${e.statusCode})')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Failed to create request')),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _callMechanic(ShopMechanic mechanic) async {
    if (mechanic.phoneNumber == null) return;
    final uri = Uri.parse('tel:${mechanic.phoneNumber}');
    if (!await launchUrl(uri)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open dialer')),
      );
    }
  }

  Future<void> _navigateToMechanic(ShopMechanic mechanic) async {
    if (mechanic.lat == null || mechanic.lon == null) return;
    final uri = Uri.https('www.google.com', '/maps/dir/', {
      if (_position != null)
        'origin': '${_position!['latitude']},${_position!['longitude']}',
      'destination': '${mechanic.lat},${mechanic.lon}',
    });
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      await launchUrl(uri);
    }
  }

  Color _ratingColor(double? rating) {
    if (rating == null) return Colors.grey;
    if (rating >= 4.5) return Colors.green;
    if (rating >= 4.0) return Colors.lightGreen;
    if (rating >= 3.5) return Colors.amber;
    if (rating >= 3.0) return Colors.orange;
    return Colors.red;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Find a Mechanic')),
      body: RefreshIndicator(
        onRefresh: _bootstrap,
        child: _loading && _mechanics.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : _error != null && _mechanics.isEmpty
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.location_off_outlined,
                              size: 48, color: scheme.onSurfaceVariant),
                          const SizedBox(height: 12),
                          Text(_error!, textAlign: TextAlign.center),
                          const SizedBox(height: 16),
                          FilledButton.tonal(
                            onPressed: _bootstrap,
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _mechanics.length + 1,
                    itemBuilder: (context, i) {
                      if (i == 0) {
                        return StaleHint(
                          isStale: _stale,
                          isOffline: !ConnectivityService.instance.isOnline,
                        );
                      }
                      final m = _mechanics[i - 1];
                      return _MechanicCard(
                        mechanic: m,
                        ratingColor: _ratingColor(m.rating),
                        onRequestJob: () => _createJobRequest(m),
                        onCall: () => _callMechanic(m),
                        onNavigate: () => _navigateToMechanic(m),
                      );
                    },
                  ),
      ),
    );
  }
}

class _MechanicCard extends StatelessWidget {
  const _MechanicCard({
    required this.mechanic,
    required this.ratingColor,
    required this.onRequestJob,
    required this.onCall,
    required this.onNavigate,
  });

  final ShopMechanic mechanic;
  final Color ratingColor;
  final VoidCallback onRequestJob;
  final VoidCallback onCall;
  final VoidCallback onNavigate;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundColor: scheme.surfaceContainerHighest,
                  backgroundImage: mechanic.logoUrl != null
                      ? NetworkImage(mechanic.logoUrl!)
                      : null,
                  child: mechanic.logoUrl == null
                      ? Text(
                          mechanic.name.substring(0, 1).toUpperCase(),
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontWeight: FontWeight.w600,
                            fontSize: 18,
                          ),
                        )
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        mechanic.name,
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w600),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      if (mechanic.distanceKm != null) ...[
                        const SizedBox(height: 2),
                        Row(
                          children: [
                            Icon(Icons.location_on_outlined,
                                size: 14, color: scheme.onSurfaceVariant),
                            const SizedBox(width: 4),
                            Text(
                              '${mechanic.distanceKm!.toStringAsFixed(1)} km',
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: scheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                if (mechanic.rating != null)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.star, size: 16, color: ratingColor),
                      const SizedBox(width: 4),
                      Text(
                        mechanic.rating!.toStringAsFixed(1),
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          color: ratingColor,
                        ),
                      ),
                      if (mechanic.reviewCount != null &&
                          mechanic.reviewCount! > 0) ...[
                        const SizedBox(width: 4),
                        Text(
                          '(${mechanic.reviewCount})',
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ],
                  ),
              ],
            ),
            if (mechanic.address != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.place_outlined,
                      size: 14, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      mechanic.address!,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: scheme.onSurfaceVariant),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ],
            if (mechanic.services.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: mechanic.services.map((s) {
                  return Chip(
                    label: Text(s, style: const TextStyle(fontSize: 11)),
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    backgroundColor: scheme.surfaceContainerHighest,
                    side: BorderSide(color: scheme.outlineVariant),
                  );
                }).toList(),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (mechanic.phoneNumber != null)
                  TextButton.icon(
                    onPressed: onCall,
                    icon: const Icon(Icons.phone, size: 16),
                    label: const Text('Call'),
                  ),
                TextButton.icon(
                  onPressed: onNavigate,
                  icon: const Icon(Icons.navigation, size: 16),
                  label: const Text('Navigate'),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: onRequestJob,
                  icon: const Icon(Icons.build, size: 16),
                  label: const Text('Request job'),
                ),
              ],
            ),
            if (mechanic.isOpen != null) ...[
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Icon(
                    mechanic.isOpen!
                        ? Icons.check_circle
                        : Icons.cancel_outlined,
                    size: 14,
                    color: mechanic.isOpen! ? Colors.green : Colors.red,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    mechanic.isOpen! ? 'Open now' : 'Closed',
                    style: TextStyle(
                      fontSize: 12,
                      color: mechanic.isOpen! ? Colors.green : Colors.red,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
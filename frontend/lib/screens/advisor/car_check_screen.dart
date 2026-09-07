import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';
import 'advisor_models.dart';

enum _VerdictColor { greatDeal, fair, overpriced, risky }

class CarCheckScreen extends StatefulWidget {
  const CarCheckScreen({super.key});

  @override
  State<CarCheckScreen> createState() => _CarCheckScreenState();
}

class _CarCheckScreenState extends State<CarCheckScreen> {
  late final AdvisorApi _advisorApi;
  final _urlController = TextEditingController();
  final _makeController = TextEditingController();
  final _modelController = TextEditingController();
  final _yearController = TextEditingController();
  final _askingController = TextEditingController();
  final _odoController = TextEditingController();
  String _condition = 'good';

  bool _submitting = false;
  AdvisorResponse? _resp;
  String? _error;

  @override
  void initState() {
    super.initState();
    _advisorApi = AdvisorApi(context.read<AuthState>().api);
  }

  @override
  void dispose() {
    _urlController.dispose();
    _makeController.dispose();
    _modelController.dispose();
    _yearController.dispose();
    _askingController.dispose();
    _odoController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final asking = double.tryParse(_askingController.text.replaceAll(RegExp(r'[^\d.]'), ''));
    if (asking == null || asking <= 0) {
      setState(() => _error = 'A valid asking price is required.');
      return;
    }
    final make = _makeController.text.trim();
    final model = _modelController.text.trim();
    final year = int.tryParse(_yearController.text.trim());
    final odometer = int.tryParse(_odoController.text.replaceAll(RegExp(r'[^\d]'), ''));

    final body = <String, dynamic>{
      'listing_url': _urlController.text.trim(),
      'make': make,
      'model': model,
      if (year != null) 'year': year,
      'asking_price': asking,
      if (odometer != null) 'odometer_km': odometer,
      if (_condition.isNotEmpty) 'condition': _condition,
      'vehicle_type': 'car',
    };

    setState(() {
      _submitting = true;
      _error = null;
      _resp = null;
    });
    try {
      final r = await _advisorApi.carCheck(body);
      if (mounted) setState(() => _resp = r);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'Failed to check this car. Try again.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Car Check')),
      body: SafeArea(
        child: _resp != null
            ? _buildResult(context)
            : _buildForm(context),
      ),
    );
  }

  Widget _buildForm(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Check a used car listing', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          TextFormField(
            controller: _urlController,
            decoration: InputDecoration(
              labelText: 'Listing URL (optional)',
              hintText: 'e.g. https://carsales.com.au/...',
              prefixIcon: const Icon(Icons.link),
              border: const OutlineInputBorder(),
            ),
            keyboardType: TextInputType.url,
          ),
          const SizedBox(height: 12),
          Text('Or enter details manually', style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: TextFormField(controller: _makeController, decoration: InputDecoration(labelText: 'Make', border: const OutlineInputBorder()))),
            const SizedBox(width: 8),
            Expanded(child: TextFormField(controller: _modelController, decoration: InputDecoration(labelText: 'Model', border: const OutlineInputBorder()))),
          ]),
          const SizedBox(height: 12),
          TextFormField(
            controller: _yearController,
            decoration: InputDecoration(labelText: 'Year', border: const OutlineInputBorder(), prefixIcon: const Icon(Icons.calendar_today)),
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(4)],
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _askingController,
            decoration: InputDecoration(labelText: 'Asking price (AUD)', border: const OutlineInputBorder(), prefixIcon: const Icon(Icons.attach_money)),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _odoController,
            decoration: InputDecoration(labelText: 'Odometer km (optional)', border: const OutlineInputBorder(), prefixIcon: const Icon(Icons.speed)),
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _condition,
            items: const [
              DropdownMenuItem(value: 'excellent', child: Text('Excellent')),
              DropdownMenuItem(value: 'good', child: Text('Good')),
              DropdownMenuItem(value: 'fair', child: Text('Fair')),
              DropdownMenuItem(value: 'poor', child: Text('Poor')),
            ],
            onChanged: (v) => setState(() => _condition = v ?? 'good'),
            decoration: const InputDecoration(labelText: 'Condition', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 20),
          _submitting
              ? const Center(child: CircularProgressIndicator())
              : ElevatedButton.icon(
                  onPressed: _submit,
                  icon: const Icon(Icons.search),
                  label: const Text('Check This Car'),
                  style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                ),
          if (_error != null) ...[const SizedBox(height: 12), Text(_error!, style: TextStyle(color: theme.colorScheme.error))],
        ],
      ),
    );
  }

  static const _verdictColors = {
    'great_deal': Color(0xFF059669), // green
    'fair': Color(0xFFCA8A04),       // amber
    'overpriced': Color(0xFFEA580C), // orange
    'risky': Color(0xFFDC2626),      // red
  };
  static const _verdictLabels = {
    'great_deal': 'Great deal',
    'fair': 'Fair price',
    'overpriced': 'Overpriced',
    'risky': 'Risky',
  };
  static const _verdictIcons = {
    'great_deal': Icons.check_circle,
    'fair': Icons.rate_review,
    'overpriced': Icons.trending_up,
    'risky': Icons.warning,
  };

  Color _verdictColor(String v) => _verdictColors[v] ?? _verdictColors['risky']!;
  String _verdictLabel(String v) => _verdictLabels[v] ?? 'Unknown';
  IconData _verdictIcon(String v) => _verdictIcons[v] ?? Icons.warning;

  Widget _resultCard(BuildContext context, String title, String value, {Color? color}) {
    final theme = Theme.of(context);
    return Card(
      child: ListTile(
        leading: color != null ? CircleAvatar(backgroundColor: color.withValues(alpha: 0.15), child: Icon(Icons.info, color: color)) : null,
        title: Text(title, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        trailing: Text(value, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
      ),
    );
  }

  Widget _buildResult(BuildContext context) {
    final data = _resp!.data;
    final d = CarCheckData.fromJson(data);
    final color = _verdictColor(d.verdict);
    final theme = Theme.of(context);
    final asking = d.askingPrice;
    final mid = d.fairValueMid;
    final deltaPct = d.deltaPct;
    final deltaAmt = d.deltaAmount;

    return RefreshIndicator(
      onRefresh: () async {
        final body = <String, dynamic>{'listing_url': _urlController.text.trim()};
        setState(() => _resp = null);
        final r = await _advisorApi.carCheck(body);
        setState(() => _resp = r);
      },
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  CircleAvatar(backgroundColor: color.withValues(alpha: 0.25), child: Icon(_verdictIcon(d.verdict), color: color, size: 32)),
                  const SizedBox(height: 8),
                  Text(_verdictLabel(d.verdict), style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700, color: color)),
                  if (deltaPct != null && mid != null && asking != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'Asking \$${asking.toInt()} vs fair \$${mid.toInt()} (${deltaPct > 0 ? "+" : ""}${deltaPct.toStringAsFixed(1)}%)',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              children: [
                if (d.fairValueLow != null && d.fairValueHigh != null) ...[
                  _Chip(label: 'Fair: \$${d.fairValueLow!.toInt()} - \$${d.fairValueHigh!.toInt()}'),
                  if (deltaAmt != null) _Chip(label: 'Delta: \$${deltaAmt!.abs().toInt()} ${deltaAmt! < 0 ? "(under)" : "(over)"}'),
                ],
                _Chip(label: 'Sample: ${d.sampleSize}'),
                _Chip(label: d.model ?? 'rule-based'),
              ],
            ),
            const SizedBox(height: 16),
            if (d.aiSummary?.isNotEmpty ?? false) ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Why', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 4),
                      Text(d.aiSummary!),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (d.redFlags.isNotEmpty) ...[
              Text('Red flags', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700, color: theme.colorScheme.error)),
              const SizedBox(height: 4),
              ...d.redFlags.map((f) => ListTile(leading: const Icon(Icons.cancel, color: Colors.red, size: 16), title: Text(f, style: theme.textTheme.bodySmall))),
              const SizedBox(height: 16),
            ],
            if (d.greenFlags.isNotEmpty) ...[
              Text('Green flags', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700, color: Colors.green)),
              const SizedBox(height: 4),
              ...d.greenFlags.map((f) => ListTile(leading: const Icon(Icons.check, color: Colors.green, size: 16), title: Text(f, style: theme.textTheme.bodySmall))),
              const SizedBox(height: 16),
            ],
            if (d.note != null && d.note!.isNotEmpty) ...[
              Text(d.note!, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              const SizedBox(height: 12),
            ],
            TextButton.icon(onPressed: () => setState(() => _resp = null), icon: const Icon(Icons.refresh), label: const Text('Check another car')),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) {
    return Chip(backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest, label: Text(label, style: Theme.of(context).textTheme.bodySmall), visualDensity: VisualDensity.compact, padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2));
  }
}

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/models.dart';

class AddFuelScreen extends StatefulWidget {
  const AddFuelScreen({super.key, required this.vehicleId, this.existing});
  final String vehicleId;
  final FuelLog? existing;

  @override
  State<AddFuelScreen> createState() => _AddFuelScreenState();
}

class _AddFuelScreenState extends State<AddFuelScreen> {
  final _formKey = GlobalKey<FormState>();
  final _date = TextEditingController();
  final _odo = TextEditingController();
  final _litres = TextEditingController();
  final _price = TextEditingController();
  final _total = TextEditingController();
  final _notes = TextEditingController();
  late bool _fullTank;
  bool _busy = false;
  bool _scanning = false;
  String? _receiptId;
  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _date.text = e.fillDate;
      _odo.text = '${e.odometerKm}';
      _litres.text = e.litres.toString();
      _price.text = e.pricePerLitre.toString();
      _total.text = e.totalCost.toString();
      _notes.text = e.notes ?? '';
      _fullTank = e.isFullTank;
      _receiptId = e.receiptId;
    } else {
      _date.text = DateTime.now().toString().substring(0, 10);
      _fullTank = true;
    }
  }

  @override
  void dispose() {
    for (final c in [_date, _odo, _litres, _price, _total, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  double? get _calcTotal {
    final l = double.tryParse(_litres.text);
    final p = double.tryParse(_price.text);
    if (l != null && p != null) {
      final t = l * p;
      _total.text = t.toStringAsFixed(2);
      return t;
    }
    return null;
  }

  Future<void> _scanReceipt() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['jpg', 'jpeg', 'png', 'webp', 'pdf'],
    );
    if (result == null || result.files.isEmpty) return;
    final picked = result.files.single;
    final List<int> bytes;
    if (picked.bytes != null) {
      bytes = picked.bytes!;
    } else if (picked.path != null) {
      bytes = await readLocalFile(picked.path!);
    } else {
      return;
    }
    setState(() => _scanning = true);
    final api = context.read<AuthState>().api;
    try {
      final data = await api.upload(
        '/vehicles/${widget.vehicleId}/fuel/receipt?ai=true',
        bytes,
        picked.name,
        mimeForFile(picked.name),
      ) as Map<String, dynamic>;
      final litres = data['litres'];
      final price = data['price_per_litre'];
      final total = data['total_cost'];
      final day = data['date'];
      setState(() {
        _receiptId = (data['receipt_id'] as String?) ?? _receiptId;
        if (litres != null) _litres.text = litres.toString();
        if (price != null) _price.text = double.parse(price.toString()).toString();
        if (total != null) _total.text = double.parse(total.toString()).toStringAsFixed(2);
        if (day != null && day.toString().isNotEmpty) _date.text = day.toString().substring(0, 10);
        if (!_calcTotalAvailable()) {}
      });
      _price.text = double.parse(_price.text.isEmpty ? '0' : _price.text).toString();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
            (data['ai_used'] == true)
                ? 'Receipt scanned — enter the odometer reading.'
                : 'Receipt uploaded — enter the details manually.',
          ),
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Scan failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _scanning = false);
    }
  }

  bool _calcTotalAvailable() => false; // no-op kept for clarity

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    final body = <String, dynamic>{
      'fill_date': _date.text,
      'odometer_km': int.parse(_odo.text),
      'litres': double.parse(_litres.text),
      'price_per_litre': double.parse(_price.text),
      'is_full_tank': _fullTank,
      if (_notes.text.isNotEmpty) 'notes': _notes.text,
      if (_total.text.isNotEmpty && double.tryParse(_total.text) != null)
        'total_cost': double.parse(_total.text),
      if (_receiptId != null) 'receipt_id': _receiptId,
    };
    final api = context.read<AuthState>().api;
    try {
      if (_isEdit) {
        await api.patch(
            '/vehicles/${widget.vehicleId}/fuel/${widget.existing!.id}', body);
      } else {
        await api.post('/vehicles/${widget.vehicleId}/fuel', body);
      }
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar:
          AppBar(title: Text(_isEdit ? 'Edit fill-up' : 'Add fill-up')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              OutlinedButton.icon(
                onPressed: _scanning ? null : _scanReceipt,
                icon: _scanning
                    ? const SizedBox(
                        height: 16,
                        width: 16,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.camera_alt_outlined),
                label: Text(_isEdit ? 'Rescan receipt' : 'Scan fuel receipt'),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _date,
                decoration: const InputDecoration(labelText: 'Date'),
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _odo,
                decoration: const InputDecoration(labelText: 'Odometer (km)'),
                keyboardType: TextInputType.number,
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _litres,
                      decoration: const InputDecoration(labelText: 'Litres'),
                      keyboardType: TextInputType.number,
                      onChanged: (_) => _calcTotal,
                      validator: (v) =>
                          v == null || v.isEmpty ? 'Required' : null,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _price,
                      decoration: const InputDecoration(
                        labelText: 'Price per litre',
                        prefixText: '\$ ',
                      ),
                      keyboardType: TextInputType.number,
                      onChanged: (_) => _calcTotal,
                      validator: (v) =>
                          v == null || v.isEmpty ? 'Required' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _total,
                decoration: const InputDecoration(
                  labelText: 'Total cost (auto)',
                  prefixText: '\$ ',
                ),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _notes,
                decoration:
                    const InputDecoration(labelText: 'Notes (optional)'),
              ),
              const SizedBox(height: 12),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Full tank'),
                value: _fullTank,
                onChanged: (v) => setState(() => _fullTank = v ?? true),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_isEdit ? 'Save changes' : 'Save fill-up'),
              ),
              if (_receiptId != null) ...[
                const SizedBox(height: 8),
                const Text('Receipt attached',
                    style: TextStyle(fontSize: 12),
                    textAlign: TextAlign.center),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
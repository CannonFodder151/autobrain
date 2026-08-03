import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class _CommonItem {
  const _CommonItem(this.name, this.partNo, this.defaultCost);
  final String name;
  final String? partNo;
  final double defaultCost;
}

const _commonItems = [
  _CommonItem('Oil change', null, 60.0),
  _CommonItem('Oil filter', 'RYCO Z89A', 25.0),
  _CommonItem('Air filter', 'RYCO A1528', 45.0),
  _CommonItem('Cabin filter', null, 35.0),
  _CommonItem('Spark plugs', 'NGK BKR6EIX', 90.0),
  _CommonItem('Brake pads', 'BENDIX DB1479', 120.0),
  _CommonItem('Brake rotors', 'DBA 2852', 260.0),
  _CommonItem('Coolant flush', null, 60.0),
  _CommonItem('Wiper blades', null, 30.0),
  _CommonItem('Battery', 'CENTURY 55D23L', 220.0),
  _CommonItem('Tyre rotation', null, 40.0),
];

class _DraftItem {
  _DraftItem(this.name, this.partNo, this.qty, this.unitCost);
  String name;
  String? partNo;
  int qty;
  double unitCost;
}

/// Create or edit a service record. Handles both past (completed) and
/// future (scheduled) services.
class ServiceFormScreen extends StatefulWidget {
  const ServiceFormScreen({super.key, required this.vehicleId, this.service});
  final String vehicleId;
  final ServiceRecord? service;

  @override
  State<ServiceFormScreen> createState() => _ServiceFormScreenState();
}

class _ServiceFormScreenState extends State<ServiceFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _date = TextEditingController();
  final _odometer = TextEditingController();
  final _workshop = TextEditingController();
  final _notes = TextEditingController();
  final _steps = TextEditingController();
  final _totalOverride = TextEditingController();
  String _type = 'scheduled';
  bool _statusCompleted = true;
  final Map<String, _DraftItem> _selectedCommon = {};
  final List<_DraftItem> _customItems = [];
  bool _busy = false;

  bool get _isEdit => widget.service != null;

  @override
  void initState() {
    super.initState();
    final s = widget.service;
    _date.text = s?.serviceDate ?? DateTime.now().toString().substring(0, 10);
    _odometer.text = (s?.odometerKm ?? 0).toString();
    _workshop.text = s?.workshop ?? '';
    _notes.text = s?.notes ?? '';
    _steps.text = (s?.steps ?? []).join('\n');
    _type = s?.serviceType ?? 'scheduled';
    _statusCompleted = s?.status != 'scheduled';
    if (s != null) {
      for (final it in s.items) {
        if (it.kind == 'part' || it.kind == 'item') {
          _selectedCommon[it.name] = _DraftItem(it.name, it.partNo, it.quantity, it.unitCost);
        }
      }
    }
  }

  @override
  void dispose() {
    for (final c in [_date, _odometer, _workshop, _notes, _steps, _totalOverride]) {
      c.dispose();
    }
    super.dispose();
  }

  double get _itemsTotal =>
      _selectedCommon.values.fold<double>(0, (a, b) => a + b.qty * b.unitCost) +
      _customItems.fold<double>(0, (a, b) => a + b.qty * b.unitCost);

  List<Map<String, dynamic>> _payloadItems() {
    final items = <Map<String, dynamic>>[
      for (final it in _selectedCommon.values)
        {
          'name': it.name,
          'part_no': it.partNo,
          'quantity': it.qty,
          'unit_cost': it.unitCost,
          'kind': it.partNo != null ? 'part' : 'item',
        },
      for (final it in _customItems)
        {
          'name': it.name,
          'part_no': it.partNo,
          'quantity': it.qty,
          'unit_cost': it.unitCost,
          'kind': 'item',
        },
    ];
    return items;
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    final override = double.tryParse(_totalOverride.text);
    final cost = override ?? _itemsTotal;
    final steps = _steps.text
        .split('\n')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    final body = {
      'service_date': _date.text,
      'odometer_km': int.tryParse(_odometer.text) ?? 0,
      'service_type': _type,
      'workshop': _workshop.text.isEmpty ? null : _workshop.text,
      'cost': cost,
      'notes': _notes.text.isEmpty ? null : _notes.text,
      'status': _statusCompleted ? 'completed' : 'scheduled',
      'steps': steps,
      'items': _payloadItems(),
    };
    try {
      final api = context.read<AuthState>().api;
      if (_isEdit) {
        await api.patch('/vehicles/${widget.vehicleId}/services/${widget.service!.id}', body);
      } else {
        await api.post('/vehicles/${widget.vehicleId}/services', body);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _addCustomItem() {
    setState(() => _customItems.add(_DraftItem('', null, 1, 0.0)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit service' : 'Log service')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Status',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      SegmentedButton<bool>(
                        segments: const [
                          ButtonSegment(
                              value: true, label: Text('Completed'), icon: Icon(Icons.check_circle_outline)),
                          ButtonSegment(
                              value: false, label: Text('Scheduled'), icon: Icon(Icons.schedule)),
                        ],
                        selected: {_statusCompleted},
                        onSelectionChanged: (s) => setState(() => _statusCompleted = s.first),
                      ),
                      if (!_statusCompleted)
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text(
                            'Scheduled services appear under Upcoming and don\'t count towards totals until marked completed.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _type,
                decoration: const InputDecoration(labelText: 'Service type'),
                items: const [
                  DropdownMenuItem(value: 'scheduled', child: Text('Scheduled')),
                  DropdownMenuItem(value: 'oil_change', child: Text('Oil change')),
                  DropdownMenuItem(value: 'repair', child: Text('Repair')),
                  DropdownMenuItem(value: 'tire', child: Text('Tyres')),
                  DropdownMenuItem(value: 'custom', child: Text('Custom')),
                ],
                onChanged: (v) => setState(() => _type = v ?? 'scheduled'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _date,
                      decoration: const InputDecoration(labelText: 'Date'),
                      validator: (v) => v == null || v.isEmpty ? 'Required' : null,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _odometer,
                      decoration: const InputDecoration(labelText: 'Odometer (km)'),
                      keyboardType: TextInputType.number,
                      validator: (v) => v == null || v.isEmpty ? 'Required' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _workshop,
                decoration: const InputDecoration(labelText: 'Workshop'),
              ),
              const SizedBox(height: 20),
              Text('Common items',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Card(
                child: Column(
                  children: [
                    for (final item in _commonItems)
                      CheckboxListTile(
                        dense: true,
                        controlAffinity: ListTileControlAffinity.leading,
                        title: Text(item.name),
                        subtitle: item.partNo != null ? Text(item.partNo!) : null,
                        value: _selectedCommon.containsKey(item.name),
                        onChanged: (v) {
                          setState(() {
                            if (v == true) {
                              _selectedCommon[item.name] =
                                  _DraftItem(item.name, item.partNo, 1, item.defaultCost);
                            } else {
                              _selectedCommon.remove(item.name);
                            }
                          });
                        },
                      ),
                  ],
                ),
              ),
              for (final entry in _selectedCommon.entries) _CommonItemEditor(entry: entry, onChanged: () => setState(() {})),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Extra items',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  TextButton.icon(
                    onPressed: _addCustomItem,
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add item'),
                  ),
                ],
              ),
              if (_customItems.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('Add as many extra parts/labour items as you like.',
                      style: TextStyle(color: Colors.grey)),
                ),
              for (var i = 0; i < _customItems.length; i++)
                _CustomItemEditor(
                  item: _customItems[i],
                  onRemove: () => setState(() => _customItems.removeAt(i)),
                  onChanged: () => setState(() {}),
                ),
              const SizedBox(height: 20),
              Text('Work steps',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              TextFormField(
                controller: _steps,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Steps (one per line)',
                  hintText: 'Inspect brakes\nReplace pads\nBed-in pads',
                ),
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('Items total',
                              style: Theme.of(context).textTheme.titleSmall),
                          Text('\$${_itemsTotal.toStringAsFixed(2)}',
                              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _totalOverride,
                        decoration: const InputDecoration(
                          labelText: 'Total cost (override)',
                          hintText: 'Leave empty to use items total',
                          prefixText: '\$ ',
                        ),
                        keyboardType: TextInputType.number,
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _notes,
                decoration: const InputDecoration(labelText: 'Notes'),
                maxLines: 3,
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _save,
                child: Text(_isEdit ? 'Save changes' : 'Save service'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CommonItemEditor extends StatelessWidget {
  const _CommonItemEditor({required this.entry, required this.onChanged});
  final MapEntry<String, _DraftItem> entry;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final item = entry.value;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 4),
        child: Row(
          children: [
            Expanded(child: Text(item.name)),
            SizedBox(
              width: 70,
              child: TextFormField(initialValue: item.qty.toString(),
                decoration: const InputDecoration(labelText: 'Qty', isDense: true),
                keyboardType: TextInputType.number,
                onChanged: (v) => item.qty = int.tryParse(v) ?? 1,
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 90,
              child: TextFormField(initialValue: item.unitCost.toStringAsFixed(0),
                decoration: const InputDecoration(labelText: 'Cost', isDense: true, prefixText: '\$ '),
                keyboardType: TextInputType.number,
                onChanged: (v) => item.unitCost = double.tryParse(v) ?? 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CustomItemEditor extends StatelessWidget {
  const _CustomItemEditor({required this.item, required this.onRemove, required this.onChanged});
  final _DraftItem item;
  final VoidCallback onRemove;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  flex: 3,
                  child: TextFormField(initialValue: item.name,
                    decoration: const InputDecoration(labelText: 'Item name', isDense: true),
                    onChanged: (v) => item.name = v,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 2,
                  child: TextFormField(initialValue: item.partNo ?? '',
                    decoration: const InputDecoration(labelText: 'Part no.', isDense: true),
                    onChanged: (v) => item.partNo = v.isEmpty ? null : v,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                SizedBox(
                  width: 70,
                  child: TextFormField(initialValue: item.qty.toString(),
                    decoration: const InputDecoration(labelText: 'Qty', isDense: true),
                    keyboardType: TextInputType.number,
                    onChanged: (v) => item.qty = int.tryParse(v) ?? 1,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextFormField(initialValue: item.unitCost.toStringAsFixed(0),
                    decoration: const InputDecoration(labelText: 'Unit cost', isDense: true, prefixText: '\$ '),
                    keyboardType: TextInputType.number,
                    onChanged: (v) => item.unitCost = double.tryParse(v) ?? 0,
                  ),
                ),
                IconButton(onPressed: onRemove, icon: const Icon(Icons.delete_outline)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}


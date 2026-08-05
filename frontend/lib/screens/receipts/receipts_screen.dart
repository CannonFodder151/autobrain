import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/models.dart';

class ReceiptsScreen extends StatefulWidget {
  const ReceiptsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ReceiptsScreen> createState() => _ReceiptsScreenState();
}

class _ReceiptsScreenState extends State<ReceiptsScreen> {
  List<Receipt> _receipts = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api.get(
              '/vehicles/${widget.vehicleId}/receipts') as List;
      _receipts = data
          .map((e) => Receipt.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'jpg', 'jpeg', 'png', 'webp'],
    );
    if (result == null || result.files.isEmpty) return;
    final picked = result.files.single;
    final filename = picked.name;
    final List<int> bytes;
    if (picked.bytes != null) {
      bytes = picked.bytes!;
    } else if (picked.path != null) {
      bytes = await readLocalFile(picked.path!);
    } else {
      return;
    }
    final api = context.read<AuthState>().api;
    try {
      await api.upload(
        '/vehicles/${widget.vehicleId}/receipts',
        bytes,
        filename,
        mimeForFile(filename),
      );
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Upload failed: $e')));
      }
    }
  }

  Future<void> _apply(Receipt r) async {
    final api = context.read<AuthState>().api;
    try {
      await api.post(
          '/vehicles/${widget.vehicleId}/receipts/${r.id}/apply-to-service', {
        'service_type': 'custom',
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Added to service history and inventory')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Receipts & parts scan')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _pickAndUpload,
        icon: const Icon(Icons.document_scanner),
        label: const Text('Scan receipt'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _receipts.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        'Scan an invoice or parts receipt to auto-extract parts, labour, cost and warranty.',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.only(bottom: 96),
                    itemCount: _receipts.length,
                    itemBuilder: (context, i) {
                      final r = _receipts[i];
                      final statusColor = switch (r.ocrStatus) {
                        'done' => Colors.green,
                        'failed' => Colors.red,
                        _ => Colors.amber,
                      };
                      return Card(
                        child: ListTile(
                          leading: const Icon(Icons.receipt_long),
                          title: Text(r.vendor ?? r.originalName ?? 'Receipt'),
                          subtitle: Text(
                            r.ocrStatus.toUpperCase(),
                            style: TextStyle(color: statusColor),
                          ),
                          trailing: r.total != null
                              ? Text('\$${r.total!.toStringAsFixed(2)}')
                              : null,
                          onTap: r.ocrStatus == 'done' ? () => _apply(r) : null,
                        ),
                      );
                    },
                  ),
      ),
    );
  }
}

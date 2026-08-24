/// Standalone wrapper for the dongle WiFi settings panel (AUT-1573).
///
/// The panel itself now lives in the OBD tab; this screen remains for the
/// settings deep link. See [DongleWifiPanel].
library;

import 'package:flutter/material.dart';

import 'dongle_wifi_panel.dart';

class DongleWifiScreen extends StatelessWidget {
  const DongleWifiScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Dongle WiFi upload')),
      body: const DongleWifiPanel(),
    );
  }
}

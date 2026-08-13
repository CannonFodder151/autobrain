/// Community Garage entry point (Garage → Social nav). Feed + My Builds tabs
/// for everyone; admin Settings moved to the AppBar 3-dot menu (AUT-502).
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth_state.dart';
import 'screens/my_builds_screen.dart';
import 'screens/server_settings.dart';
import 'screens/social_screen.dart';

class CommunityGarageScreen extends StatelessWidget {
  const CommunityGarageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final isAdmin = context.watch<AuthState>().isAdmin;
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Community Garage'),
          actions: [
            if (isAdmin)
              PopupMenuButton<String>(
                tooltip: 'Community Garage options',
                onSelected: (_) {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                        builder: (_) => const ServerSettings()),
                  );
                },
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'settings', child: Text('Settings')),
                ],
              ),
          ],
          bottom: const TabBar(tabs: [
            Tab(text: 'Feed'),
            Tab(text: 'My Builds'),
          ]),
        ),
        body: const TabBarView(children: [
          SocialScreen(),
          MyBuildsScreen(),
        ]),
      ),
    );
  }
}

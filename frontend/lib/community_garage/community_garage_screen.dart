/// Community Garage entry point (Garage → Social nav). Feed for everyone;
/// admin toggles only for admins.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth_state.dart';
import 'screens/server_settings.dart';
import 'screens/social_screen.dart';

class CommunityGarageScreen extends StatelessWidget {
  const CommunityGarageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final isAdmin = context.watch<AuthState>().isAdmin;
    return DefaultTabController(
      length: isAdmin ? 2 : 1,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Community Garage'),
          bottom: isAdmin
              ? const TabBar(tabs: [
                  Tab(text: 'Feed'),
                  Tab(text: 'Settings'),
                ])
              : null,
        ),
        body: isAdmin
            ? const TabBarView(children: [
                SocialScreen(),
                ServerSettings(),
              ])
            : const SocialScreen(),
      ),
    );
  }
}

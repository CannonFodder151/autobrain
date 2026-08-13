/// Community Garage entry point (Garage → Social nav). Feed for everyone;
/// My Builds for the caller's own posts (AUT-501); admin toggles for admins.
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
    final tabCount = isAdmin ? 3 : 2;
    return DefaultTabController(
      length: tabCount,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Community Garage'),
          bottom: TabBar(tabs: [
            const Tab(text: 'Feed'),
            const Tab(text: 'My Builds'),
            if (isAdmin) const Tab(text: 'Settings'),
          ]),
        ),
        body: TabBarView(children: [
          const SocialScreen(),
          const MyBuildsScreen(),
          if (isAdmin) const ServerSettings(),
        ]),
      ),
    );
  }
}

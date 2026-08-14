/// Community Garage entry point (Garage → Social nav). Feed + My Builds +
/// Issues Blog tabs for everyone; admin Settings moved to the AppBar 3-dot
/// menu (AUT-502). Issues Blog is the blog-style help board (AUT-627).
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth_state.dart';
import 'screens/issues_blog_screen.dart';
import 'screens/my_builds_screen.dart';
import 'screens/server_settings.dart';
import 'screens/social_screen.dart';

class CommunityGarageScreen extends StatelessWidget {
  const CommunityGarageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final isAdmin = context.watch<AuthState>().isAdmin;
    return DefaultTabController(
      length: 3,
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
            Tab(text: 'Issues Blog'),
          ]),
        ),
        body: const TabBarView(children: [
          SocialScreen(),
          MyBuildsScreen(),
          IssuesBlogScreen(),
        ]),
      ),
    );
  }
}

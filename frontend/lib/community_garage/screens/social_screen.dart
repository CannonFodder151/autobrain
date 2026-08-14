/// Community Garage feed — Facebook-style vertical scroll (AUT-294 §4.1).
///
/// Premium gate first (free accounts never see feed data, rev 4). If the
/// server returns "Disabled by your admin" the feature is off. Federation
/// source is decided server-side: on → hub feed, off → local-only.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/config.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/premium_gate.dart';
import '../widgets/social_card.dart';
import 'social_compose.dart';
import 'social_post_detail.dart';
import 'share_link_view.dart';

class SocialScreen extends StatefulWidget {
  const SocialScreen({super.key});

  @override
  State<SocialScreen> createState() => _SocialScreenState();
}

class _SocialScreenState extends State<SocialScreen> {
  List<SocialBuild> _builds = const [];
  bool _loading = true;
  bool _disabled = false;
  String? _error;
  bool _loadingMore = false;
  final _scroll = ScrollController();
  final _searchController = TextEditingController();
  Timer? _debounce;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (_query != value.trim()) {
        _query = value.trim();
        _load();
      }
    });
  }

  void _clearSearch() {
    _debounce?.cancel();
    _query = '';
    _searchController.clear();
    _load();
  }

  void _onScroll() {
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 400) {
      _loadMore();
    }
  }

  Future<void> _load() async {
    final auth = context.read<AuthState>();
    if (auth.freeAccount) {
      setState(() => _loading = false);
      return;
    }
    final api = SocialApi(auth.api);
    setState(() {
      _loading = true;
      _error = null;
      _disabled = false;
    });
    try {
      final builds = await api.feed(q: _query);
      setState(() => _builds = builds);
    } on ApiException catch (e) {
      if (e.message.contains('Disabled by your admin')) {
        setState(() => _disabled = true);
      } else {
        setState(() => _error = e.message);
      }
    } catch (_) {
      setState(() =>
          _error = 'Could not reach the server. Check your connection.');
    }
    setState(() => _loading = false);
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _loading) return;
    setState(() => _loadingMore = true);
    try {
      final more = await SocialApi(context.read<AuthState>().api)
          .feed(q: _query);
      if (more.isNotEmpty && mounted) {
        final known = _builds.map((b) => b.id).toSet();
        setState(() => _builds = [
          ..._builds,
          ...more.where((b) => !known.contains(b.id)),
        ]);
      }
    } catch (_) {}
    setState(() => _loadingMore = false);
  }

  Future<void> _refresh() async {
    await _load();
  }

  Future<void> _share(SocialBuild build) async {
    final api = SocialApi(context.read<AuthState>().api);
    if (build.isRemote) {
      if (!mounted) return;
      await _showShareDialog(
        title: 'View this build',
        message:
            'This build was shared from another server. Open it to view it on '
            'your own AutoBrain instance.',
        actions: [
          _shareAction(
            label: 'View build',
            onPressed: () {
              Navigator.of(context).pop();
              Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => SocialPostDetailScreen(
                      postId: build.id, initial: build)));
            },
          ),
        ],
      );
      return;
    }
    try {
      final link = await api.createShareLink(build.id);
      final fullLink = '${_originBase()}${link.url}';
      if (!mounted) return;
      await _showShareDialog(
        title: 'Share this build',
        message: fullLink,
        selectable: true,
        actions: [
          _shareAction(
            label: 'Copy link',
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: fullLink));
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                  content: Text('Link copied to clipboard')));
              Navigator.of(context).pop();
            },
          ),
          _shareAction(
            label: 'View',
            filled: true,
            onPressed: () {
              Navigator.of(context).pop();
              Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ShareLinkView(token: link.token)));
            },
          ),
        ],
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Could not create share link: $e')));
      }
    }
  }

  /// Small dialog helper for the share flow (AUT-676): the shared link is
  /// copyable and can be opened in-app so it renders on the user's own
  /// instance. A close button is always appended.
  Future<void> _showShareDialog({
    required String title,
    required String message,
    required List<Widget> actions,
    bool selectable = false,
  }) {
    return showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: selectable
            ? SelectableText(message)
            : Text(message),
        actions: [
          ...actions,
          _shareAction(
            label: 'Close',
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  Widget _shareAction({
    required String label,
    required VoidCallback onPressed,
    bool filled = false,
  }) {
    return filled
        ? FilledButton(onPressed: onPressed, child: Text(label))
        : TextButton(onPressed: onPressed, child: Text(label));
  }

  String _originBase() {
    final base = AppConfig.apiBase;
    return base.replaceFirst(RegExp(r'/api/v1/?$'), '');
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      floatingActionButton: (auth.premium && !_disabled)
          ? FloatingActionButton.extended(
              onPressed: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const SocialComposeScreen()));
                _refresh();
              },
              icon: const Icon(Icons.add),
              label: const Text('Share a build'),
            )
          : null,
      body: _body(auth),
    );
  }

  Widget _body(AuthState auth) {
    if (auth.freeAccount) return const PremiumGate();
    if (_disabled) {
      return const _DisabledView();
    }
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return _ErrorView(message: _error!, onRetry: _load);
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
          child: TextField(
            controller: _searchController,
            onChanged: _onSearchChanged,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Search posts by make, model, caption or author',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _query.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.clear),
                      tooltip: 'Clear search',
                      onPressed: _clearSearch,
                    ),
              isDense: true,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(24),
              ),
            ),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _refresh,
            child: _builds.isEmpty
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      SizedBox(height: 160),
                      Center(
                        child: Text(
                          _query.isEmpty
                              ? 'Nothing here yet — be the first to share a build.'
                              : 'No posts match "$_query".',
                          style: const TextStyle(color: Colors.grey),
                        ),
                      ),
                    ],
                  )
                : ListView.separated(
                    controller: _scroll,
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(12, 4, 12, 88),
                    itemCount: _builds.length + 1,
                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                    itemBuilder: (_, i) {
                      if (i >= _builds.length) {
                        return _loadingMore
                            ? const Padding(
                                padding: EdgeInsets.all(12),
                                child: Center(child: CircularProgressIndicator()),
                              )
                            : const SizedBox.shrink();
                      }
                      final build = _builds[i];
                      return SocialCard(
                        post: build,
                        onTap: () async {
                          await Navigator.of(context).push(MaterialPageRoute(
                              builder: (_) => SocialPostDetailScreen(
                                  postId: build.id, initial: build)));
                          _refresh();
                        },
                        onShare: () => _share(build),
                        onDelete: (auth.isAdmin && !build.isRemote)
                            ? () => _delete(build)
                            : null,
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }

  Future<void> _delete(SocialBuild build) async {
    final api = SocialApi(context.read<AuthState>().api);
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Unshare build?'),
        content: Text('Remove "${build.title ?? 'this build'}" from the feed?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Unshare')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.deletePost(build.id);
      if (mounted) {
        setState(() => _builds = _builds.where((b) => b.id != build.id).toList());
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Could not delete: $e')));
      }
    }
  }
}

class _DisabledView extends StatelessWidget {
  const _DisabledView();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.people_outline, size: 64, color: scheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text('Community Garage has been disabled by your admin.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}

/// Issues Blog tab — blog-archive list with keyword search, tag chips and
/// status filter (all server-side + deterministic, AUT-627). Reverse-
/// chronological with keyset cursor pagination.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/issue_card.dart';
import '../widgets/premium_gate.dart';
import 'issue_compose_screen.dart';
import 'issue_detail_screen.dart';

class IssuesBlogScreen extends StatefulWidget {
  const IssuesBlogScreen({super.key});

  @override
  State<IssuesBlogScreen> createState() => _IssuesBlogScreenState();
}

class _IssuesBlogScreenState extends State<IssuesBlogScreen> {
  List<SocialIssuePost> _posts = const [];
  bool _loading = true;
  bool _disabled = false;
  String? _error;
  bool _loadingMore = false;
  String? _nextCursor;
  final _scroll = ScrollController();
  final _searchController = TextEditingController();
  Timer? _debounce;
  String _query = '';
  String? _tag;
  IssueStatus? _status;
  bool _mine = false;

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
        _reload();
      }
    });
  }

  void _onScroll() {
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 400) {
      _loadMore();
    }
  }

  void _reload() {
    _nextCursor = null;
    _load();
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
      final result = await api.issues(
          q: _query, tag: _tag, status: _status, cursor: _nextCursor, mine: _mine);
      setState(() {
        _posts = result.items;
        _nextCursor = result.nextCursor;
      });
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
    if (_loadingMore || _loading || _nextCursor == null) return;
    setState(() => _loadingMore = true);
    try {
      final result = await SocialApi(context.read<AuthState>().api).issues(
          q: _query, tag: _tag, status: _status, cursor: _nextCursor, mine: _mine);
      if (mounted) {
        setState(() {
          final known = _posts.map((p) => p.id).toSet();
          _posts = [
            ..._posts,
            ...result.items.where((p) => !known.contains(p.id)),
          ];
          _nextCursor = result.nextCursor;
        });
      }
    } catch (_) {}
    setState(() => _loadingMore = false);
  }

  Future<void> _refresh() async => _reload();

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      floatingActionButton: (auth.premium && !_disabled)
          ? FloatingActionButton.extended(
              onPressed: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const IssueComposeScreen()));
                _reload();
              },
              icon: const Icon(Icons.help_outline),
              label: const Text('Ask for help'),
            )
          : null,
      body: _body(auth),
    );
  }

  Widget _body(AuthState auth) {
    if (auth.freeAccount) {
      return const PremiumGate(
          lockedReason:
              'The Issues Blog is a premium member feature — get help from real owners.');
    }
    if (_disabled) return const _DisabledView();
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return _ErrorView(message: _error!, onRetry: _reload);
    }
    return Column(
      children: [
        _filterBar(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _refresh,
            child: _posts.isEmpty
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      const SizedBox(height: 160),
                      Center(
                        child: Text(
                          _mine
                              ? 'No issues here yet — tap "Ask for help" to post your first one.'
                              : _query.isEmpty && _tag == null && _status == null
                                  ? 'No issues yet — tap "Ask for help" to post the first one.'
                                  : 'No issues match your filters.',
                          style: const TextStyle(color: Colors.grey),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ],
                  )
                : ListView.separated(
                    controller: _scroll,
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(12, 4, 12, 88),
                    itemCount: _posts.length + 1,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (_, i) {
                      if (i >= _posts.length) {
                        return _loadingMore
                            ? const Padding(
                                padding: EdgeInsets.all(12),
                                child:
                                    Center(child: CircularProgressIndicator()))
                            : const SizedBox.shrink();
                      }
                      final post = _posts[i];
                      return IssueCard(
                        post: post,
                        onTap: () async {
                          await Navigator.of(context).push(MaterialPageRoute(
                              builder: (_) =>
                                  IssueDetailScreen(postId: post.id, initial: post)));
                          _reload();
                        },
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }

  Widget _filterBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _searchController,
            onChanged: _onSearchChanged,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Search issues by problem or detail',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _query.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.clear),
                      tooltip: 'Clear search',
                      onPressed: () {
                        _searchController.clear();
                        _query = '';
                        _reload();
                      },
                    ),
              isDense: true,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
            ),
          ),
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                _filterChip(
                  label: 'My Issues',
                  selected: _mine,
                  onSelected: () => setState(() {
                    _mine = !_mine;
                    _reload();
                  }),
                ),
                _filterChip(
                  label: 'All',
                  selected: _tag == null && _status == null && !_mine,
                  onSelected: () => setState(() {
                    _mine = false;
                    _tag = null;
                    _status = null;
                    _reload();
                  }),
                ),
                for (final t in issueTagVocabulary.take(8))
                  _filterChip(
                    label: t,
                    selected: _tag == t,
                    onSelected: () => setState(() {
                      _tag = _tag == t ? null : t;
                      _reload();
                    }),
                  ),
                const SizedBox(width: 8),
                for (final s in IssueStatus.values)
                  _filterChip(
                    label: s.name,
                    selected: _status == s,
                    onSelected: () => setState(() {
                      _status = _status == s ? null : s;
                      _reload();
                    }),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _filterChip({
    required String label,
    required bool selected,
    required VoidCallback onSelected,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: ChoiceChip(
        label: Text(label,
            style: TextStyle(
                fontSize: 12,
                color: selected ? scheme.onPrimaryContainer : scheme.onSurfaceVariant)),
        selected: selected,
        showCheckmark: false,
        visualDensity: VisualDensity.compact,
        onSelected: (_) => onSelected(),
      ),
    );
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

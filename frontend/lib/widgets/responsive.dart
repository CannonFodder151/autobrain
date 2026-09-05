import 'package:flutter/material.dart';

/// Desktop layout breakpoints for the web app.
///
/// AutoBrain is designed mobile-first; on desktop the content is capped to a
/// comfortable reading width so very wide screens don't stretch forms, cards
/// and maps into unusable whitespace (AUT-2526).
class Breakpoints {
  static const desktop = 1100.0;
  static const wideDesktop = 1400.0;
}

class _ResponsiveData {
  final bool isDesktop;
  final bool isWideDesktop;
  final double maxWidth;

  const _ResponsiveData(this.isDesktop, this.isWideDesktop, this.maxWidth);
}

/// Extension on [BuildContext] that resolves the current desktop layout.
extension ResponsiveContext on BuildContext {
  bool get isDesktop =>
      switch (MediaQuery.of(this).size.shortestSide) {
        >= Breakpoints.desktop => true,
        _ => false,
      };

  bool get isWideDesktop =>
      MediaQuery.of(this).size.shortestSide >= Breakpoints.wideDesktop;

  /// The capped content width for the current screen.
  ///
  /// On mobile this is `double.infinity` (no cap). On desktop it grows from
  /// [Breakpoints.desktop] up to [Breakpoints.wideDesktop] then stays fixed so
  /// 1920px+ screens don't sprawl.
  double get contentMaxWidth {
    final w = MediaQuery.of(this).size.width;
    if (w < Breakpoints.desktop) return double.infinity;
    if (w > Breakpoints.wideDesktop) return Breakpoints.wideDesktop;
    return w;
  }
}

/// A layout widget that centers its child and caps its width on desktop.
///
/// Wrap a Scaffold's body (or a scrollable Column) with this to prevent
/// forms and cards from stretching beyond [Breakpoints.wideDesktop] on
/// large screens. On mobile it behaves as a plain pass-through.
class CenteredMaxWidth extends StatelessWidget {
  const CenteredMaxWidth({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
    this.maxWidth,
  });

  final Widget child;
  final EdgeInsets padding;
  final double? maxWidth;

  @override
  Widget build(BuildContext context) {
    final effectiveMax = maxWidth ?? Breakpoints.wideDesktop;
    return LayoutBuilder(
      builder: (_, constraints) {
        if (constraints.maxWidth <= effectiveMax) {
          return padding == EdgeInsets.zero
              ? child
              : Padding(padding: padding, child: child);
        }
        return Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: effectiveMax),
            child: padding == EdgeInsets.zero
                ? child
                : Padding(padding: padding, child: child),
          ),
        );
      },
    );
  }
}

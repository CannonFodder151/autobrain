import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// Responsive max-width wrapper for main content screens on desktop web.
///
/// On web at >= 1280px wide, constrains the body content to [maxWidth] and
/// centers it within a `SafeArea`. Below that breakpoint behavior is unchanged.
class DesktopMaxWidth extends StatelessWidget {
  const DesktopMaxWidth({
    super.key,
    required this.child,
    this.maxWidth = 1280,
    this.padding = EdgeInsets.zero,
  });

  final Widget child;
  final double maxWidth;
  final EdgeInsets padding;

  static bool get isDesktop =>
      kIsWeb && MediaQueryData.fromView(PlatformDispatcher.instance.implicitView!).size.width >= 1280;

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) return child;

    final isDesktopSize = MediaQueryData.fromView(
            PlatformDispatcher.instance.implicitView!)
        .size
        .width >=
    1280;

    if (!isDesktopSize) return child;

    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: SafeArea(
          top: false,
          bottom: false,
          child: Padding(
            padding: padding,
            child: child,
          ),
        ),
      ),
    );
  }
}

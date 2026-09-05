import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// Centered card for auth-style screens on desktop web.
///
/// Constrains content to [maxWidth] and caps vertical space so the login /
/// signup form never stretches beyond a comfortable reading width.
class CenteredMaxWidth extends StatelessWidget {
  const CenteredMaxWidth({
    super.key,
    required this.child,
    this.maxWidth = 460,
    this.verticalPadding = 24,
    this.horizontalPadding = 16,
  });

  final Widget child;
  final double maxWidth;
  final double verticalPadding;
  final double horizontalPadding;

  static bool get isDesktop =>
      kIsWeb && MediaQueryData.fromView(PlatformDispatcher.instance.implicitView!).size.width >= 1280;

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) return child;
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: maxWidth,
          maxHeight: MediaQuery.of(context).size.height - verticalPadding * 2,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: horizontalPadding, vertical: verticalPadding),
          child: SingleChildScrollView(child: child),
        ),
      ),
    );
  }
}

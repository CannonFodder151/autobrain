import 'package:flutter/material.dart';

/// Fixed breakpoints per AUT-2525.
class Breakpoints {
  static const double mobileMax = 599;
  static const double tabletMax = 1023;
  static const double desktopMin = 1024;
  static const double maxContentWidth = 1200;
  static const EdgeInsetsGeometry defaultPadding = EdgeInsets.symmetric(horizontal: 16);
  static const EdgeInsetsGeometry widePadding = EdgeInsets.symmetric(horizontal: 32);
}

enum Breakpoint { mobile, tablet, desktop }

extension _BreakpointX on double {
  Breakpoint get asBreakpoint {
    if (this >= Breakpoints.desktopMin) return Breakpoint.desktop;
    if (this > Breakpoints.mobileMax) return Breakpoint.tablet;
    return Breakpoint.mobile;
  }
}

class ResponsiveLayout extends InheritedWidget {
  const ResponsiveLayout({
    super.key,
    required this.breakpoint,
    required this.constraints,
    required this.maxWidth,
    required super.child,
  });

  final Breakpoint breakpoint;
  final BoxConstraints constraints;
  final double maxWidth;

  static ResponsiveLayout? of(BuildContext context) {
    return context.dependOnInheritedWidgetOfExactType<ResponsiveLayout>();
  }

  @override
  bool updateShouldNotify(ResponsiveLayout old) =>
      old.breakpoint != breakpoint || old.maxWidth != maxWidth;
}

class ResponsiveScaffold extends StatelessWidget {
  const ResponsiveScaffold({
    super.key,
    required this.child,
    this.padding,
    this.center = true,
    this.backgroundColor,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final bool center;
  final Color? backgroundColor;

  static Breakpoint of(BuildContext context) =>
      ResponsiveLayout.of(context)?.breakpoint ?? Breakpoint.mobile;

  @override
  Widget build(BuildContext context) {
    final bg = backgroundColor ?? Theme.of(context).scaffoldBackgroundColor;
    return LayoutBuilder(
      builder: (ctx, constraints) {
        final maxWidth = constraints.maxWidth > Breakpoints.desktopMin
            ? Breakpoints.maxContentWidth
            : constraints.maxWidth;
        final bp = constraints.maxWidth.asBreakpoint;
        final effectivePadding =
            padding ?? (bp == Breakpoint.desktop ? Breakpoints.widePadding : Breakpoints.defaultPadding);

        final content = ResponsiveLayout(
          breakpoint: bp,
          constraints: constraints,
          maxWidth: maxWidth,
          child: child,
        );

        if (center) {
          return ColoredBox(
            color: bg,
            child: Center(
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: maxWidth),
                child: Padding(padding: effectivePadding, child: content),
              ),
            ),
          );
        }
        return ColoredBox(
          color: bg,
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxWidth),
              child: Padding(padding: effectivePadding, child: content),
            ),
          ),
        );
      },
    );
  }
}

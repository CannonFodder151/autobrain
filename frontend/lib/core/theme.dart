import 'package:flutter/material.dart';

/// AutoBrain brand theme.
///
/// Dark-first futuristic automotive styling: near-black surfaces, electric
/// blue primary (#00B7FF), frosted cards, 16px rounded corners.
class AppTheme {
  // Brand palette
  static const bgDark = Color(0xFF050505);
  static const surfaceDark = Color(0xFF0B0F16);
  static const cardDark = Color(0xFF11151D);
  static const primaryBlue = Color(0xFF00B7FF);
  static const accentBlue = Color(0xFF007BFF);
  static const secondaryBlue = Color(0xFF1A4DFF);
  static const white = Color(0xFFF5F7FA);
  static const grayText = Color(0xFF9CA3AF);

  static const lightScaffold = Color(0xFFF5F7FA);

  static ThemeData light() =>
      _base(Brightness.light, lightScaffold, isDark: false);

  static ThemeData dark() =>
      _base(Brightness.dark, surfaceDark, isDark: true);

  static ThemeData _base(Brightness brightness, Color scaffold,
      {required bool isDark}) {
    final scheme = ColorScheme.fromSeed(
      seedColor: primaryBlue,
      brightness: brightness,
      primary: isDark ? primaryBlue : accentBlue,
      secondary: secondaryBlue,
      surface: isDark ? surfaceDark : lightScaffold,
      error: const Color(0xFFEF4444),
    );
    final card = isDark ? cardDark : Colors.white;
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scaffold,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: scaffold,
        titleTextStyle: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.2,
          color: scheme.onSurface,
        ),
        iconTheme: IconThemeData(color: isDark ? primaryBlue : accentBlue),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(
            color: isDark
                ? primaryBlue.withOpacity(0.12)
                : accentBlue.withOpacity(0.10),
          ),
        ),
        margin: EdgeInsets.zero,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 44),
          backgroundColor: isDark ? primaryBlue : accentBlue,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: isDark ? const Color(0xFF1C212A) : const Color(0xFFF0F2F5),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(
            color: isDark
                ? primaryBlue.withOpacity(0.14)
                : accentBlue.withOpacity(0.14),
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: scheme.primary, width: 1.4),
        ),
      ),
      listTileTheme: const ListTileThemeData(iconColor: null),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
      dividerTheme: DividerThemeData(
        color: (isDark ? primaryBlue : accentBlue).withOpacity(0.10),
      ),
    );
  }
}

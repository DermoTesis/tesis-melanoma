import 'package:flutter/material.dart';

/// Tokens de color tomados de los mockups de Dermavía.
abstract final class AppColors {
  // Marca / acción / validado
  static const primary = Color(0xFF1D6B4F);
  static const primaryDark = Color(0xFF14503A);
  static const primarySoft = Color(0xFFD6E8DE);
  static const successBg = Color(0xFFE3F1EA);
  static const successAccent = Color(0xFF5FB58C);

  // Superficies
  static const background = Color(0xFFF4F8F5);
  static const canvas = Color(0xFFE6EDE8);
  static const surface = Colors.white;
  static const surfaceMuted = Color(0xFFEEF3F0);
  static const cameraBg = Color(0xFF0B1410);
  static const ink = Color(0xFF13241C);

  // Texto
  static const text = Color(0xFF13241C);
  static const textBody = Color(0xFF2C3D35);
  static const textMuted = Color(0xFF4D5E56);
  static const textSubtle = Color(0xFF5B6B63);
  static const textDisabled = Color(0xFF8A9A92);

  // Bordes
  static const border = Color(0xFFD4E0D9);
  static const borderStrong = Color(0xFFC9D8CF);
  static const borderDashed = Color(0xFF9FB5A9);
  static const divider = Color(0xFFE2EBE6);
  static const disabled = Color(0xFFC9D8CF);
  static const iconMuted = Color(0xFFC3D0C9);

  // Pendiente / incertidumbre
  static const warningBg = Color(0xFFFBF1D9);
  static const warningChip = Color(0xFFF3E3B6);
  static const warningText = Color(0xFF6B4A06);
  static const warningAccent = Color(0xFFC8961F);

  // Probabilidad alta / error
  static const errorBg = Color(0xFFFBE9E4);
  static const errorChip = Color(0xFFF6D6CD);
  static const errorText = Color(0xFF8A2F1F);
  static const error = Color(0xFFB4432F);
  static const errorBorder = Color(0xFFD97A64);
  static const errorSurface = Color(0xFFFDF3F0);
  static const errorCardBorder = Color(0xFFEAB7A9);

  // Placeholder de lesión (patrón rayado de los mockups)
  static const lesionA = Color(0xFFD8C3B6);
  static const lesionB = Color(0xFFE7D7CC);
  static const lesionDarkA = Color(0xFFC9AD9C);
  static const lesionDarkB = Color(0xFFDCC6B8);

  // Fototipos de Fitzpatrick
  static const phototypes = [
    Color(0xFFF3DFCF),
    Color(0xFFE9C9AB),
    Color(0xFFD4A883),
    Color(0xFFB07F58),
    Color(0xFF7D5438),
    Color(0xFF4B3122),
  ];
}

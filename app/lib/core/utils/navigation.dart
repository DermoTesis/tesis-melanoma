import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Vuelve atrás si hay historial; si no, regresa al panel de casos.
void popOrPanel(BuildContext context) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go('/casos');
  }
}

/// Botón atrás que nunca deja al usuario sin salida.
class SmartBackButton extends StatelessWidget {
  const SmartBackButton({super.key, this.close = false});
  final bool close;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: Icon(close ? Icons.close : Icons.arrow_back),
      onPressed: () => popOrPanel(context),
    );
  }
}

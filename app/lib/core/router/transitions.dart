import 'package:animations/animations.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Transiciones entre pantallas, con los patrones de movimiento de Material.
///
/// Cada ruta elige una según su relación con la pantalla de la que viene:
///
/// - [fadeThrough]: cambio de contexto sin relación jerárquica. La pantalla anterior se
///   desvanece y la nueva aparece con un leve acercamiento. Se usa en la entrada y salida
///   de la sesión (login, aceptación del alcance, panel, administración), entre las
///   pestañas de la barra inferior y al confirmar el envío de un caso.
/// - [drillIn]: del listado al detalle (eje Z). La nueva pantalla crece desde el centro
///   y al volver se encoge. Se usa en el caso, el paciente, la validación, el informe y
///   las pantallas del administrador.
/// - [step]: pasos de un mismo flujo (eje X). La nueva pantalla entra desde la derecha y
///   al volver regresa hacia la izquierda. Se usa en el registro de un caso (buscar
///   paciente, registrarlo, consentimiento, fotos y datos clínicos) y al recuperar o
///   activar la cuenta desde el login.
///
/// Si el sistema tiene las animaciones desactivadas (accesibilidad), Flutter acorta
/// todas estas transiciones a casi nada sin que haga falta tratarlo aquí.
enum AppTransition { fadeThrough, drillIn, step }

abstract final class AppMotion {
  /// Duración de Material para las transiciones entre pantallas.
  static const duration = Duration(milliseconds: 300);
}

/// Página de go_router que entra y sale con la transición [type].
Page<void> transitionPage(GoRouterState state, AppTransition type, Widget child) {
  return CustomTransitionPage<void>(
    key: state.pageKey,
    name: state.name,
    child: child,
    transitionDuration: AppMotion.duration,
    reverseTransitionDuration: AppMotion.duration,
    transitionsBuilder: (context, animation, secondaryAnimation, child) =>
        buildTransition(type, animation, secondaryAnimation, child),
  );
}

Widget buildTransition(
  AppTransition type,
  Animation<double> animation,
  Animation<double> secondaryAnimation,
  Widget child,
) {
  return switch (type) {
    AppTransition.fadeThrough => FadeThroughTransition(
        animation: animation,
        secondaryAnimation: secondaryAnimation,
        child: child,
      ),
    AppTransition.drillIn => SharedAxisTransition(
        animation: animation,
        secondaryAnimation: secondaryAnimation,
        transitionType: SharedAxisTransitionType.scaled,
        child: child,
      ),
    AppTransition.step => SharedAxisTransition(
        animation: animation,
        secondaryAnimation: secondaryAnimation,
        transitionType: SharedAxisTransitionType.horizontal,
        child: child,
      ),
  };
}

/// Contenedor de las pestañas del especialista (Casos · Pacientes · Alertas · Perfil).
///
/// Hace lo mismo que el `IndexedStack` de go_router (cada pestaña conserva su estado y
/// su historial), pero al cambiar de pestaña la anterior se desvanece y la nueva aparece
/// con [AppTransition.fadeThrough].
class FadeThroughBranches extends StatefulWidget {
  const FadeThroughBranches({super.key, required this.currentIndex, required this.children});

  final int currentIndex;
  final List<Widget> children;

  @override
  State<FadeThroughBranches> createState() => _FadeThroughBranchesState();
}

class _FadeThroughBranchesState extends State<FadeThroughBranches>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: AppMotion.duration, value: 1);

  /// Pestaña que se está desvaneciendo, mientras dura la transición.
  int? _leaving;

  @override
  void didUpdateWidget(FadeThroughBranches oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentIndex == widget.currentIndex) return;
    _leaving = oldWidget.currentIndex;
    _controller.forward(from: 0).whenCompleteOrCancel(() {
      if (mounted && !_controller.isAnimating) setState(() => _leaving = null);
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        for (var i = 0; i < widget.children.length; i++) _branch(i),
      ],
    );
  }

  // La estructura de widgets es la misma para todas las pestañas en todo momento (solo
  // cambian las animaciones), para que ninguna pierda su estado al cambiar de pestaña.
  Widget _branch(int i) {
    final active = i == widget.currentIndex;
    final leaving = !active && i == _leaving;
    return Offstage(
      offstage: !active && !leaving,
      child: TickerMode(
        enabled: active,
        child: IgnorePointer(
          ignoring: !active,
          child: ExcludeSemantics(
            excluding: !active,
            child: FadeThroughTransition(
              animation: active ? _controller : kAlwaysCompleteAnimation,
              secondaryAnimation: leaving ? _controller : kAlwaysDismissedAnimation,
              child: widget.children[i],
            ),
          ),
        ),
      ),
    );
  }
}

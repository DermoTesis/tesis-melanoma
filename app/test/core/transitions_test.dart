import 'package:animations/animations.dart';
import 'package:dermavia/core/router/transitions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

/// Pestaña con estado propio, para comprobar que no se pierde al cambiar de pestaña.
class _Counter extends StatefulWidget {
  const _Counter(this.label);
  final String label;

  @override
  State<_Counter> createState() => _CounterState();
}

class _CounterState extends State<_Counter> {
  var _n = 0;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: TextButton(
            onPressed: () => setState(() => _n++),
            child: Text('${widget.label} $_n'),
          ),
        ),
      );
}

GoRouter _router() => GoRouter(
      initialLocation: '/a',
      routes: [
        StatefulShellRoute(
          builder: (_, _, shell) => Scaffold(
            body: shell,
            bottomNavigationBar: Row(children: [
              TextButton(onPressed: () => shell.goBranch(0), child: const Text('ir A')),
              TextButton(onPressed: () => shell.goBranch(1), child: const Text('ir B')),
            ]),
          ),
          navigatorContainerBuilder: (_, shell, children) =>
              FadeThroughBranches(currentIndex: shell.currentIndex, children: children),
          branches: [
            StatefulShellBranch(routes: [
              GoRoute(path: '/a', builder: (_, _) => const _Counter('A')),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(path: '/b', builder: (_, _) => const _Counter('B')),
            ]),
          ],
        ),
        GoRoute(
          path: '/detalle',
          pageBuilder: (_, s) => transitionPage(s, AppTransition.drillIn, const Text('detalle')),
        ),
        GoRoute(
          path: '/paso',
          pageBuilder: (_, s) => transitionPage(s, AppTransition.step, const Text('paso')),
        ),
      ],
    );

void main() {
  group('Transiciones entre pantallas', () {
    testWidgets('las pestañas cambian con fundido y conservan su estado', (tester) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.tap(find.text('A 0'));
      await tester.pump();
      expect(find.text('A 1'), findsOneWidget);

      await tester.tap(find.text('ir B'));
      await tester.pump();
      await tester.pump(AppMotion.duration ~/ 10);
      // A mitad de camino la pestaña anterior aún se ve, desvaneciéndose.
      expect(find.text('A 1'), findsOneWidget);
      expect(find.text('B 0'), findsOneWidget);

      await tester.pumpAndSettle();
      expect(find.text('A 1'), findsNothing, reason: 'queda fuera de escena');
      expect(find.text('B 0'), findsOneWidget);

      await tester.tap(find.text('ir A'));
      await tester.pumpAndSettle();
      expect(find.text('A 1'), findsOneWidget, reason: 'el contador de A no se reinicia');
      expect(find.text('B 0'), findsNothing);
    });

    testWidgets('el detalle entra en el eje Z y los pasos de un flujo en el eje X',
        (tester) async {
      final router = _router();
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));

      SharedAxisTransitionType axisOf(String text) => tester
          .widget<SharedAxisTransition>(find
              .ancestor(of: find.text(text), matching: find.byType(SharedAxisTransition))
              .first)
          .transitionType;

      router.push('/detalle');
      await tester.pumpAndSettle();
      expect(axisOf('detalle'), SharedAxisTransitionType.scaled);

      router.push('/paso');
      await tester.pumpAndSettle();
      expect(axisOf('paso'), SharedAxisTransitionType.horizontal);

      router.pop();
      router.pop();
      await tester.pumpAndSettle();
      expect(find.text('A 0'), findsOneWidget);
    });
  });
}

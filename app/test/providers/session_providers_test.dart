import 'dart:async';

import 'package:dermavia/data/mock/mock_backend.dart';
import 'package:dermavia/data/mock/mock_repositories.dart';
import 'package:dermavia/data/mock/seed_data.dart';
import 'package:dermavia/domain/models/clinical_case.dart';
import 'package:dermavia/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Como el backend real visto desde la app: la primera lectura trae los casos de
/// la sesión de ese momento y la siguiente tarda (red, arranque en frío).
class _SlowCases extends MockCaseRepository {
  _SlowCases(super.b, this.firstRead);

  final List<ClinicalCase> firstRead;
  var reads = 0;

  @override
  Stream<List<ClinicalCase>> watchCasesForPatient(String patientId) {
    reads++;
    return reads == 1 ? Stream.value(firstRead) : StreamController<List<ClinicalCase>>().stream;
  }
}

/// Al cambiar de usuario no puede quedar en pantalla nada leído con la cuenta
/// anterior, ni siquiera mientras carga lo nuevo (en la nube se veía unos segundos).
void main() {
  late MockBackend b;
  late ProviderContainer container;
  late _SlowCases cases;
  late ClinicalCase caseOfOtherDoctor;

  /// Deja que lleguen los valores de los streams y se apliquen los cambios.
  Future<void> settle() async {
    for (var i = 0; i < 3; i++) {
      await Future<void>.delayed(Duration.zero);
      await container.pump();
    }
  }

  Future<void> signIn(String email, String password) async {
    await container.read(authRepositoryProvider).signIn(email, password);
    await settle();
  }

  Future<void> signOut() async {
    await container.read(authRepositoryProvider).signOut();
    await settle();
  }

  setUp(() {
    b = MockBackend(latency: Duration.zero, analysisDuration: Duration.zero, schedulerInterval: null);
    caseOfOtherDoctor = b.cases.values.first;
    cases = _SlowCases(b, [caseOfOtherDoctor]);
    container = ProviderContainer(overrides: [
      mockBackendProvider.overrideWithValue(b),
      caseRepositoryProvider.overrideWithValue(cases),
    ]);
    // Mantiene viva la sesión, como el router de la app.
    container.listen(authStateProvider, (_, _) {});
  });

  tearDown(() {
    container.dispose();
    b.dispose();
  });

  test('al cerrar sesión los datos se vacían de inmediato', () async {
    await signIn(DemoCredentials.specialistEmail, DemoCredentials.specialistPassword);
    final sub = container.listen(patientCasesProvider('p-jmamani'), (_, _) {});
    await settle();
    expect(sub.read().value, [caseOfOtherDoctor]);

    await signOut();
    expect(sub.read().value, isEmpty);
    sub.close();
  });

  test('la siguiente cuenta no recibe el valor anterior mientras carga', () async {
    await signIn(DemoCredentials.specialistEmail, DemoCredentials.specialistPassword);
    var sub = container.listen(patientCasesProvider('p-jmamani'), (_, _) {});
    await settle();
    expect(sub.read().value, [caseOfOtherDoctor]);

    // La app vuelve a /login y se cierran las pantallas.
    sub.close();
    await signOut();

    await signIn(DemoCredentials.specialistEmail, DemoCredentials.specialistPassword);
    final seen = <AsyncValue<List<ClinicalCase>>>[];
    sub = container.listen(patientCasesProvider('p-jmamani'), (_, next) => seen.add(next),
        fireImmediately: true);
    await settle();
    expect(cases.reads, 2);
    expect(sub.read().isLoading, isTrue);
    expect(seen.every((s) => !s.hasValue), isTrue,
        reason: 'no debe mostrarse nada leído en la sesión anterior');
    sub.close();
  });
}

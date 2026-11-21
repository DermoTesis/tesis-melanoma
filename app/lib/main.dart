import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

import 'app.dart';
import 'data/remote/backend_config.dart';
import 'data/remote/local_case_store.dart';
import 'firebase_options.dart';
import 'providers/repository_providers.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  Intl.defaultLocale = 'es_PE';
  await initializeDateFormatting('es_PE');
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

  final config = BackendConfig.fromEnvironment();
  final overrides = [backendConfigProvider.overrideWithValue(config)];
  if (config.isRemote) {
    // Cola offline, fotos de los casos y orden manual guardados en el dispositivo.
    final store = LocalCaseStore();
    await store.load();
    overrides.add(localCaseStoreProvider.overrideWithValue(store));
  }
  if (config.usesFirebase) {
    // Solo en modo `nube`: el simulado, el servidor local y las pruebas no
    // dependen de Firebase (CONEXION_NUBE.md, N2).
    await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
    final auth = FirebaseAuth.instance;
    await auth.setLanguageCode('es');
    // La app pide el login cada vez que se abre (N5): la sesión que Firebase
    // guardó en el dispositivo se cierra para que empiece y termine junto con
    // la de la app.
    await auth.signOut();
  }
  runApp(ProviderScope(overrides: overrides, child: const DermaviaApp()));
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

import 'app.dart';
import 'data/remote/backend_config.dart';
import 'data/remote/local_case_store.dart';
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
  runApp(ProviderScope(overrides: overrides, child: const DermaviaApp()));
}

// Opciones de Firebase del proyecto `tesis-dermavia` (CONEXION_NUBE.md, C1), con el
// mismo formato que genera `flutterfire configure`. Salen de la app Android registrada
// en Firebase (pe.edu.upc.dermavia), igual que android/app/google-services.json.
//
// La API key es pública por diseño: identifica el proyecto, no da acceso a datos. La API
// exige un ID token y Firestore niega el acceso de clientes.

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (defaultTargetPlatform != TargetPlatform.android) {
      throw UnsupportedError('Dermavía solo está configurada para Android.');
    }
    return android;
  }

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyDiIb9LOsDL11Zk-XVp2WFge-xuyObjkKI',
    appId: '1:432424057783:android:33d690028819e52d21c632',
    messagingSenderId: '432424057783',
    projectId: 'tesis-dermavia',
    storageBucket: 'tesis-dermavia.firebasestorage.app',
  );
}

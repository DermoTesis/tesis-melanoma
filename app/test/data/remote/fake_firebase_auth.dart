import 'package:dermavia/data/remote/token_provider.dart';
import 'package:firebase_auth/firebase_auth.dart' show FirebaseAuthException;

/// Firebase Authentication simulado (CONEXION_NUBE.md, N12).
class FakeFirebaseAuth implements FirebaseAuthGateway {
  String? signInError;
  String? tokenError;
  String? resetError;
  String? uid;
  final resets = <String>[];

  @override
  Future<String> signInWithEmailAndPassword(String email, String password) async {
    if (signInError != null) throw FirebaseAuthException(code: signInError!);
    return uid = 'uid-${email.split('@').first}';
  }

  @override
  Future<String?> idToken() async {
    if (tokenError != null) throw FirebaseAuthException(code: tokenError!);
    return uid == null ? null : 'token-de-$uid';
  }

  @override
  Future<void> signOut() async => uid = null;

  @override
  Future<void> sendPasswordResetEmail(String email) async {
    if (resetError != null) throw FirebaseAuthException(code: resetError!);
    resets.add(email);
  }
}

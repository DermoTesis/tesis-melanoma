import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../../core/errors/app_exception.dart';

/// El dispositivo no pudo hablar con el backend (sin red, servidor caído o
/// tiempo agotado). La cola offline usa este tipo para decidir si reintenta.
class NetworkException extends AppException {
  const NetworkException()
      : super('Sin conexión con el servidor. Revisa tu conexión e inténtalo otra vez.',
            code: 'unavailable');
}

/// Cliente REST del backend de Dermavía (INTEGRACION_BACKEND.md, I0 e I12).
///
/// Agrega `Authorization: Bearer <token>`, manda y recibe JSON y traduce los
/// errores `{"error": {"codigo", "mensaje"}}` a [AppException] con el mismo
/// `code`, para que las pantallas sigan funcionando igual que con el backend
/// simulado.
class ApiClient {
  ApiClient({
    required String baseUrl,
    required Future<String?> Function() token,
    http.Client? client,
    this.timeout = const Duration(seconds: 20),
    this.onUnauthenticated,
    this.onReachability,
  })  : _baseUrl = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl,
        _token = token,
        _http = client ?? http.Client();

  final String _baseUrl;
  final Future<String?> Function() _token;
  final http.Client _http;
  final Duration timeout;

  /// Se llama ante un 401 (`unauthenticated`): la sesión expiró.
  final void Function()? onUnauthenticated;

  /// Se llama con `true` tras cada respuesta y con `false` ante un fallo de red.
  final void Function(bool reachable)? onReachability;

  Uri uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$_baseUrl$path').replace(queryParameters: query);

  Future<dynamic> get(String path, {Map<String, String>? query, Duration? timeout}) =>
      _send('GET', path, query: query, timeout: timeout);

  Future<dynamic> post(String path, {Object? body, Duration? timeout}) =>
      _send('POST', path, body: body, timeout: timeout);

  Future<dynamic> put(String path, {Object? body}) => _send('PUT', path, body: body);

  Future<dynamic> patch(String path, {Object? body}) => _send('PATCH', path, body: body);

  Future<dynamic> delete(String path) => _send('DELETE', path);

  Future<dynamic> _send(String method, String path,
      {Map<String, String>? query, Object? body, Duration? timeout}) async {
    final request = http.Request(method, uri(path, query));
    request.headers['Accept'] = 'application/json';
    final token = await _token();
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json; charset=utf-8';
      request.body = jsonEncode(body);
    }
    final response = await _execute(request, timeout ?? this.timeout);
    if (response.statusCode == 204 || response.bodyBytes.isEmpty) {
      if (response.statusCode >= 400) throw _errorFrom(response);
      return null;
    }
    if (response.statusCode >= 400) throw _errorFrom(response);
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  /// Carga directa a la URL firmada de Cloud Storage (o al almacén del
  /// servidor local): sin el token de la app y con los encabezados que indicó
  /// el backend (I19).
  Future<void> upload(String url, Uint8List bytes,
      {String method = 'PUT', Map<String, String> headers = const {}}) async {
    final request = http.Request(method, Uri.parse(url))
      ..headers.addAll(headers)
      ..bodyBytes = bytes;
    final response = await _execute(request, const Duration(seconds: 60));
    if (response.statusCode >= 400) {
      throw const AppException('No se pudo cargar la foto. Inténtalo otra vez.',
          code: 'upload-failed');
    }
  }

  /// Descarga una imagen desde una URL firmada de lectura.
  Future<Uint8List> download(String url) async {
    final response = await _execute(http.Request('GET', Uri.parse(url)), timeout);
    if (response.statusCode >= 400) {
      throw const AppException('No se pudo descargar la foto del caso.', code: 'download-failed');
    }
    return response.bodyBytes;
  }

  Future<http.Response> _execute(http.BaseRequest request, Duration timeout) async {
    try {
      final streamed = await _http.send(request).timeout(timeout);
      final response = await http.Response.fromStream(streamed).timeout(timeout);
      onReachability?.call(true);
      return response;
    } on TimeoutException {
      onReachability?.call(false);
      throw const NetworkException();
    } on SocketException {
      onReachability?.call(false);
      throw const NetworkException();
    } on http.ClientException {
      onReachability?.call(false);
      throw const NetworkException();
    }
  }

  AppException _errorFrom(http.Response response) {
    String? code;
    String? message;
    try {
      final json = jsonDecode(utf8.decode(response.bodyBytes));
      final error = json is Map ? json['error'] : null;
      if (error is Map) {
        code = error['codigo'] as String?;
        message = error['mensaje'] as String?;
      }
    } on FormatException {
      // Respuesta que no es JSON (p. ej. un proxy): se usa el mensaje genérico.
    }
    final exception = mapError(response.statusCode, code, message);
    if (exception.code == 'unauthenticated') onUnauthenticated?.call();
    return exception;
  }

  /// Traduce un error del backend a la excepción que esperan las pantallas.
  static AppException mapError(int status, String? code, String? message) {
    switch (code) {
      case 'permission-denied':
        return message == null ? const PermissionDeniedException() : PermissionDeniedException(message);
      case 'consent-required':
        return const ConsentRequiredException();
      case 'validation-required':
        return const ValidationRequiredException();
      case 'unauthenticated':
        return AppException(message ?? 'Tu sesión expiró. Inicia sesión otra vez.',
            code: 'unauthenticated');
    }
    if (code != null) {
      return AppException(message ?? 'No se pudo completar la operación.', code: code);
    }
    if (status == 401) {
      return const AppException('Tu sesión expiró. Inicia sesión otra vez.', code: 'unauthenticated');
    }
    if (status >= 500) {
      return const AppException('El servidor no pudo completar la operación. Inténtalo más tarde.',
          code: 'internal');
    }
    return AppException(message ?? 'No se pudo completar la operación.', code: 'error');
  }

  void close() => _http.close();
}

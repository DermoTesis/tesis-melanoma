import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../domain/models/clinical_case.dart';
import 'codecs.dart';

/// Caso guardado en el dispositivo mientras no hay conexión (RF-02.4, RNF-08).
/// El `requestId` viaja como `id_solicitud`: el backend devuelve el caso ya
/// creado si la app lo reenvía, así que reintentar nunca lo duplica (I18).
class QueuedCase {
  const QueuedCase({
    required this.requestId,
    required this.patientId,
    required this.clinicalData,
    required this.createdAt,
    required this.imagePaths,
    this.lastError,
  });

  final String requestId;
  final String patientId;
  final ClinicalData clinicalData;
  final DateTime createdAt;
  final Map<ImageView, String> imagePaths;

  /// Último rechazo del backend (p. ej. consentimiento revocado).
  final String? lastError;

  /// Id temporal con el que la app muestra el caso hasta tener el del backend.
  String get localId => 'local-$requestId';

  QueuedCase withError(String? error) => QueuedCase(
        requestId: requestId,
        patientId: patientId,
        clinicalData: clinicalData,
        createdAt: createdAt,
        imagePaths: imagePaths,
        lastError: error,
      );

  ClinicalCase toCase() {
    CaseImage image(ImageView view) => CaseImage(
          view: view,
          localPath: imagePaths[view],
        );
    return ClinicalCase(
      id: localId,
      patientId: patientId,
      status: CaseStatus.registrado,
      createdAt: createdAt,
      foto1: image(ImageView.foto1),
      foto2: image(ImageView.foto2),
      clinicalData: clinicalData,
      queuedOffline: true,
      lastError: lastError,
    );
  }

  Json toJson() => {
        'request_id': requestId,
        'patient_id': patientId,
        'clinical_data': clinicalDataToJson(clinicalData),
        'created_at': createdAt.toUtc().toIso8601String(),
        'images': {for (final e in imagePaths.entries) imageViewCodes[e.key]!: e.value},
        'last_error': lastError,
      };

  factory QueuedCase.fromJson(Json j) => QueuedCase(
        requestId: j['request_id'] as String,
        patientId: j['patient_id'] as String,
        clinicalData: clinicalDataFromJson(j['clinical_data'] as Json),
        createdAt: parseDateTime(j['created_at']),
        imagePaths: _imagesFromJson(j['images'] as Map),
        lastError: j['last_error'] as String?,
      );
}

Map<ImageView, String> _imagesFromJson(Map json) => {
      for (final view in ImageView.values)
        if (json[imageViewCodes[view]] != null) view: json[imageViewCodes[view]] as String,
    };

/// Datos que la app guarda en el dispositivo cuando usa el backend real: la
/// cola offline, la equivalencia entre ids locales y del backend, la ruta de
/// las fotos de cada caso capturado aquí (el backend no las devuelve en las
/// listas) y el orden manual del panel (RF-06.2, el backend no lo guarda).
class LocalCaseStore {
  LocalCaseStore({SharedPreferencesAsync? prefs, Future<Directory> Function()? photosDir})
      : _prefs = prefs ?? SharedPreferencesAsync(),
        _photosDir = photosDir ?? _defaultPhotosDir;

  /// Sin persistencia: para pruebas.
  LocalCaseStore.memory()
      : _prefs = null,
        _photosDir = null;

  static const _kQueue = 'dermavia.cola_offline';
  static const _kResolved = 'dermavia.ids_resueltos';
  static const _kImages = 'dermavia.fotos_locales';
  static const _kOrder = 'dermavia.orden_manual';

  final SharedPreferencesAsync? _prefs;
  final Future<Directory> Function()? _photosDir;

  final queue = <QueuedCase>[];
  final resolvedIds = <String, String>{};
  final localImages = <String, Map<ImageView, String>>{};
  var manualOrder = <String>[];

  static Future<Directory> _defaultPhotosDir() async {
    final base = await getApplicationDocumentsDirectory();
    return Directory('${base.path}/casos').create(recursive: true);
  }

  Future<void> load() async {
    final prefs = _prefs;
    if (prefs == null) return;
    final rawQueue = await prefs.getString(_kQueue);
    final rawResolved = await prefs.getString(_kResolved);
    final rawImages = await prefs.getString(_kImages);
    queue
      ..clear()
      ..addAll([
        if (rawQueue != null)
          for (final q in jsonDecode(rawQueue) as List) QueuedCase.fromJson(q as Json),
      ]);
    resolvedIds
      ..clear()
      ..addAll(rawResolved == null ? {} : (jsonDecode(rawResolved) as Map).cast<String, String>());
    localImages
      ..clear()
      ..addAll({
        if (rawImages != null)
          for (final e in (jsonDecode(rawImages) as Map).entries)
            e.key as String: _imagesFromJson(e.value as Map),
      });
    manualOrder = await prefs.getStringList(_kOrder) ?? [];
  }

  Future<void> _save() async {
    final prefs = _prefs;
    if (prefs == null) return;
    await prefs.setString(_kQueue, jsonEncode([for (final q in queue) q.toJson()]));
    await prefs.setString(_kResolved, jsonEncode(resolvedIds));
    await prefs.setString(
        _kImages,
        jsonEncode({
          for (final e in localImages.entries)
            e.key: {for (final i in e.value.entries) imageViewCodes[i.key]!: i.value},
        }));
    await prefs.setStringList(_kOrder, manualOrder);
  }

  /// Copia las fotos a la carpeta de la app: las de la cámara quedan en una
  /// carpeta temporal que el sistema puede borrar antes de que vuelva la red.
  Future<Map<ImageView, String>> keepPhotos(String requestId, Map<ImageView, String> paths) async {
    final dirOf = _photosDir;
    if (dirOf == null) return paths;
    final dir = await dirOf();
    return {
      for (final e in paths.entries)
        e.key: (await File(e.value).copy(
                '${dir.path}/${requestId}_${imageViewCodes[e.key]}${_extension(e.value)}'))
            .path,
    };
  }

  static String _extension(String path) {
    final dot = path.lastIndexOf('.');
    return dot < 0 ? '.jpg' : path.substring(dot).toLowerCase();
  }

  Future<void> enqueue(QueuedCase q) async {
    queue.removeWhere((x) => x.requestId == q.requestId);
    queue.add(q);
    await _save();
  }

  Future<void> markFailed(String requestId, String error) async {
    final i = queue.indexWhere((x) => x.requestId == requestId);
    if (i < 0) return;
    queue[i] = queue[i].withError(error);
    await _save();
  }

  /// El caso ya existe en el backend con [remoteId]: sale de la cola.
  Future<void> resolve(QueuedCase q, String remoteId) async {
    queue.removeWhere((x) => x.requestId == q.requestId);
    resolvedIds[q.localId] = remoteId;
    localImages[remoteId] = q.imagePaths;
    await _save();
  }

  Future<void> setLocalImages(String caseId, Map<ImageView, String> paths) async {
    localImages[caseId] = paths;
    await _save();
  }

  Future<void> setManualOrder(List<String> ids) async {
    manualOrder = List.of(ids);
    await _save();
  }
}

import 'prediction.dart';

/// Secuencia obligatoria de estados del caso (sección 5.2.4):
/// REGISTRADO → EN_ANALISIS → PENDIENTE_VALIDACION → VALIDADO → CERRADO.
enum CaseStatus {
  registrado,
  enAnalisis,
  errorAnalisis,
  pendienteValidacion,
  validado,
  cerrado,
}

extension CaseStatusLabel on CaseStatus {
  String get label {
    switch (this) {
      case CaseStatus.registrado:
        return 'Registrado';
      case CaseStatus.enAnalisis:
        return 'En análisis';
      case CaseStatus.errorAnalisis:
        return 'Error';
      case CaseStatus.pendienteValidacion:
        return 'Pendiente';
      case CaseStatus.validado:
        return 'Validado';
      case CaseStatus.cerrado:
        return 'Cerrado';
    }
  }

  String get code {
    switch (this) {
      case CaseStatus.registrado:
        return 'REGISTRADO';
      case CaseStatus.enAnalisis:
        return 'EN_ANALISIS';
      case CaseStatus.errorAnalisis:
        return 'ERROR_ANALISIS';
      case CaseStatus.pendienteValidacion:
        return 'PENDIENTE_VALIDACION';
      case CaseStatus.validado:
        return 'VALIDADO';
      case CaseStatus.cerrado:
        return 'CERRADO';
    }
  }
}

/// Las dos fotos dermatoscópicas de la misma lesión (RF-02.1). El modelo no
/// distingue cuál es cuál: es simétrico y se entrenó con pares al azar.
enum ImageView { foto1, foto2 }

extension ImageViewLabel on ImageView {
  String get label => this == ImageView.foto1 ? 'Foto 1' : 'Foto 2';
}

enum CaptureSource { camara, galeria }

/// Una de las dos imágenes obligatorias del caso (RF-02.1).
class CaseImage {
  const CaseImage({
    required this.view,
    required this.source,
    this.localPath,
    this.width,
    this.height,
  });

  final ImageView view;
  final CaptureSource source;

  /// Ruta local del archivo. Es nula en los casos de ejemplo sembrados.
  final String? localPath;
  final int? width;
  final int? height;
}

enum OnsetTime { menos3Meses, entre3y12Meses, masDe1Anio, noSabe }

extension OnsetTimeLabel on OnsetTime {
  String get label {
    switch (this) {
      case OnsetTime.menos3Meses:
        return '< 3 meses';
      case OnsetTime.entre3y12Meses:
        return '3–12 meses';
      case OnsetTime.masDe1Anio:
        return '> 1 año';
      case OnsetTime.noSabe:
        return 'No sabe';
    }
  }
}

enum Symptom { cambioTamano, picor, sangrado, cambioColor, dolor }

extension SymptomLabel on Symptom {
  String get label {
    switch (this) {
      case Symptom.cambioTamano:
        return 'Cambio de tamaño';
      case Symptom.picor:
        return 'Picor';
      case Symptom.sangrado:
        return 'Sangrado';
      case Symptom.cambioColor:
        return 'Cambio de color';
      case Symptom.dolor:
        return 'Dolor';
    }
  }
}

/// Información clínica complementaria (RF-02.3).
class ClinicalData {
  const ClinicalData({
    required this.ubicacionLesion,
    required this.tiempoAparicion,
    this.sintomas = const {},
  });

  final String ubicacionLesion;
  final OnsetTime tiempoAparicion;
  final Set<Symptom> sintomas;

  String get sintomasLabel => sintomas.isEmpty
      ? 'Ninguno referido'
      : sintomas.map((s) => s.label).join(', ');
}

/// Observación clínica interna: visible solo para personal médico y
/// excluida del informe exportable (RF-06.3).
class InternalNote {
  const InternalNote({
    required this.text,
    required this.authorName,
    required this.createdAt,
  });

  final String text;
  final String authorName;
  final DateTime createdAt;
}

class ClinicalCase {
  const ClinicalCase({
    required this.id,
    required this.patientId,
    required this.uidMedico,
    required this.status,
    required this.createdAt,
    required this.foto1,
    required this.foto2,
    required this.clinicalData,
    this.prediction,
    this.suggestion,
    this.queuedOffline = false,
    this.analysisAttempts = 0,
    this.internalNotes = const [],
  });

  /// Identificador visible, p. ej. "CASO-0201".
  final String id;
  final String patientId;
  final String uidMedico;
  final CaseStatus status;
  final DateTime createdAt;
  final CaseImage foto1;
  final CaseImage foto2;
  final ClinicalData clinicalData;
  final Prediction? prediction;

  /// Sugerencia de exámenes adicionales, editable por el especialista.
  final String? suggestion;

  /// El caso se guardó en el dispositivo sin conexión (RNF-08).
  final bool queuedOffline;
  final int analysisAttempts;
  final List<InternalNote> internalNotes;

  bool get isPendingValidation => status == CaseStatus.pendienteValidacion;

  Duration pendingFor(DateTime now) => now.difference(createdAt);

  ClinicalCase copyWith({
    CaseStatus? status,
    Prediction? prediction,
    String? suggestion,
    bool clearSuggestion = false,
    bool? queuedOffline,
    int? analysisAttempts,
    List<InternalNote>? internalNotes,
  }) {
    return ClinicalCase(
      id: id,
      patientId: patientId,
      uidMedico: uidMedico,
      status: status ?? this.status,
      createdAt: createdAt,
      foto1: foto1,
      foto2: foto2,
      clinicalData: clinicalData,
      prediction: prediction ?? this.prediction,
      suggestion: clearSuggestion ? null : (suggestion ?? this.suggestion),
      queuedOffline: queuedOffline ?? this.queuedOffline,
      analysisAttempts: analysisAttempts ?? this.analysisAttempts,
      internalNotes: internalNotes ?? this.internalNotes,
    );
  }
}

/// Borrador del caso mientras el médico captura imágenes y datos.
class CaseDraft {
  const CaseDraft({
    required this.patientId,
    this.foto1,
    this.foto2,
  });

  final String patientId;
  final CaseImage? foto1;
  final CaseImage? foto2;

  bool get hasBothImages => foto1 != null && foto2 != null;

  CaseDraft copyWith({
    CaseImage? foto1,
    CaseImage? foto2,
    bool clearFoto1 = false,
    bool clearFoto2 = false,
  }) {
    return CaseDraft(
      patientId: patientId,
      foto1: clearFoto1 ? null : (foto1 ?? this.foto1),
      foto2:
          clearFoto2 ? null : (foto2 ?? this.foto2),
    );
  }
}

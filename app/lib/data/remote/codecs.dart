// Conversión entre el JSON de la API (backend/dermavia/presentacion/esquemas.py)
// y los modelos de lib/domain/models (INTEGRACION_BACKEND.md, sección 3).
//
// Las fechas del backend llegan en UTC (ISO 8601) y se pasan a la hora local;
// `fecha_nacimiento` llega como `YYYY-MM-DD`.

import '../../domain/models/audit_event.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../domain/models/report.dart';
import '../../domain/models/user.dart';
import '../../domain/models/validation.dart';

typedef Json = Map<String, dynamic>;

// --- Valores de los enums (I11) ---

T _decode<T>(Map<T, String> codes, Object? value, String field) {
  for (final entry in codes.entries) {
    if (entry.value == value) return entry.key;
  }
  throw FormatException('Valor desconocido en $field: $value');
}

const lesionClassCodes = {
  LesionClass.melanoma: 'melanoma',
  LesionClass.noMelanoma: 'no_melanoma',
};

const caseStatusCodes = {
  CaseStatus.registrado: 'REGISTRADO',
  CaseStatus.enAnalisis: 'EN_ANALISIS',
  CaseStatus.errorAnalisis: 'ERROR_ANALISIS',
  CaseStatus.pendienteValidacion: 'PENDIENTE_VALIDACION',
  CaseStatus.validado: 'VALIDADO',
  CaseStatus.cerrado: 'CERRADO',
};

const sexCodes = {Sex.femenino: 'femenino', Sex.masculino: 'masculino'};

const phototypeCodes = {
  Phototype.i: 'I',
  Phototype.ii: 'II',
  Phototype.iii: 'III',
  Phototype.iv: 'IV',
  Phototype.v: 'V',
  Phototype.vi: 'VI',
};

const onsetCodes = {
  OnsetTime.menos3Meses: 'menos_3_meses',
  OnsetTime.entre3y12Meses: 'entre_3_y_12_meses',
  OnsetTime.masDe1Anio: 'mas_de_1_anio',
  OnsetTime.noSabe: 'no_sabe',
};

const symptomCodes = {
  Symptom.cambioTamano: 'cambio_tamano',
  Symptom.picor: 'picor',
  Symptom.sangrado: 'sangrado',
  Symptom.cambioColor: 'cambio_color',
  Symptom.dolor: 'dolor',
};

const decisionCodes = {
  ValidationDecision.confirmar: 'confirmar',
  ValidationDecision.corregir: 'corregir',
  ValidationDecision.descartar: 'descartar',
};

const roleCodes = {UserRole.especialista: 'especialista', UserRole.admin: 'admin'};

const accountStatusCodes = {
  AccountStatus.pendienteActivacion: 'PENDIENTE_ACTIVACION',
  AccountStatus.activo: 'ACTIVO',
};

const confidenceCodes = {
  PredictionConfidence.sinAlerta: 'sin_alerta',
  PredictionConfidence.baja: 'baja',
  PredictionConfidence.ambigua: 'ambigua',
  PredictionConfidence.alta: 'alta',
};

/// `TipoEvento` del backend (I10). `anonimizacion` todavía no existe allí.
const auditTypeCodes = {
  AuditType.altaCuenta: 'alta_cuenta',
  AuditType.activacionCuenta: 'activacion_cuenta',
  AuditType.aceptacionAlcance: 'aceptacion_alcance',
  AuditType.cambioRol: 'cambio_permisos',
  AuditType.registroPaciente: 'registro_paciente',
  AuditType.consentimiento: 'consentimiento',
  AuditType.revocacionConsentimiento: 'revocacion_consentimiento',
  AuditType.registroCaso: 'registro_caso',
  AuditType.prediccion: 'prediccion',
  AuditType.errorAnalisis: 'error_analisis',
  AuditType.validacion: 'validacion',
  AuditType.cierreCaso: 'cierre_caso',
  AuditType.alertaVencido: 'alerta_vencido',
};

/// Vistas del backend (I3): nombres neutros `a` y `b`, en el orden de las
/// entradas del modelo.
const imageViewCodes = {ImageView.foto1: 'a', ImageView.foto2: 'b'};

// --- Fechas ---

DateTime parseDateTime(Object? value) => DateTime.parse(value as String).toLocal();

DateTime? parseDateTimeOrNull(Object? value) => value == null ? null : parseDateTime(value);

/// `YYYY-MM-DD` como fecha local a medianoche.
DateTime parseDate(Object? value) {
  final d = DateTime.parse(value as String);
  return DateTime(d.year, d.month, d.day);
}

String formatDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

// --- Identidad ---

AppUser userFromJson(Json j) => AppUser(
      uid: j['uid'] as String,
      role: _decode(roleCodes, j['rol'], 'rol'),
      dni: j['dni'] as String,
      nombres: j['nombres'] as String,
      correo: j['correo'] as String,
      status: _decode(accountStatusCodes, j['estado'], 'estado'),
      establecimiento: j['establecimiento'] as String,
      clinicalAccess: j['acceso_clinico'] as bool,
      cmp: j['numero_colegiatura'] as String?,
      fechaVerificacion: parseDateTimeOrNull(j['fecha_verificacion']),
      termsAcceptedAt: parseDateTimeOrNull(j['fecha_aceptacion_terminos']),
    );

/// Un tipo de evento que la app no conoce no rompe la bitácora: se omite.
AuditEvent? auditEventFromJson(Json j) {
  final type = auditTypeCodes.entries
      .where((e) => e.value == j['tipo'])
      .map((e) => e.key)
      .firstOrNull;
  if (type == null) return null;
  return AuditEvent(
    id: j['id'] as String,
    type: type,
    reference: j['referencia'] as String,
    actorName: j['actor_nombre'] as String,
    timestamp: parseDateTime(j['fecha']),
  );
}

// --- Pacientes ---

Consent consentFromJson(Json j) => Consent(
      otorgado: j['otorgado'] as bool,
      fechaOtorgamiento: parseDateTime(j['fecha_otorgamiento']),
      medicoNombre: j['medico_nombre'] as String,
      fechaRevocacion: parseDateTimeOrNull(j['fecha_revocacion']),
    );

Patient patientFromJson(Json j) => Patient(
      id: j['id'] as String,
      numeroHistoriaClinica: j['numero_historia_clinica'] as String,
      nombres: j['nombres'] as String,
      fechaNacimiento: parseDate(j['fecha_nacimiento']),
      sexo: _decode(sexCodes, j['sexo'], 'sexo'),
      fototipo: _decode(phototypeCodes, j['fototipo'], 'fototipo'),
      uidMedicoRegistro: j['uid_medico_registro'] as String,
      consent: j['consentimiento'] == null ? null : consentFromJson(j['consentimiento'] as Json),
    );

Json patientToJson({
  required String numeroHistoriaClinica,
  required String nombres,
  required DateTime fechaNacimiento,
  required Sex sexo,
  required Phototype fototipo,
}) =>
    {
      'numero_historia_clinica': numeroHistoriaClinica,
      'nombres': nombres,
      'fecha_nacimiento': formatDate(fechaNacimiento),
      'sexo': sexCodes[sexo],
      'fototipo': phototypeCodes[fototipo],
    };

// --- Casos ---

Prediction predictionFromJson(Json j) => Prediction(
      probabilidadMalignidad: (j['probabilidad_malignidad'] as num).toDouble(),
      clasePredicha: _decode(lesionClassCodes, j['clase_predicha'], 'clase_predicha'),
      umbralOperativo: (j['linea_alerta'] as num).toDouble(),
      banda: confidenceCodes.entries
          .where((e) => e.value == j['banda'])
          .map((e) => e.key)
          .firstOrNull,
      versionModelo: j['version_modelo'] as String,
      fechaInferencia: parseDateTime(j['fecha_inferencia']),
    );

ClinicalData clinicalDataFromJson(Json j) => ClinicalData(
      ubicacionLesion: j['ubicacion_lesion'] as String,
      tiempoAparicion: _decode(onsetCodes, j['tiempo_aparicion'], 'tiempo_aparicion'),
      sintomas: {
        for (final s in j['sintomas'] as List) _decode(symptomCodes, s, 'sintomas'),
      },
    );

Json clinicalDataToJson(ClinicalData d) => {
      'ubicacion_lesion': d.ubicacionLesion.trim(),
      'tiempo_aparicion': onsetCodes[d.tiempoAparicion],
      'sintomas': [for (final s in d.sintomas) symptomCodes[s]],
    };

/// Caso del backend. Las imágenes combinan la copia local (si el caso se
/// capturó en este dispositivo) con las URL firmadas del detalle.
ClinicalCase caseFromJson(Json j, {Map<ImageView, String> localPaths = const {}}) {
  final urls = (j['urls_imagenes'] as Map?)?.cast<String, String>() ?? const {};
  CaseImage image(ImageView view) => CaseImage(
        view: view,
        localPath: localPaths[view],
        remoteUrl: urls[imageViewCodes[view]],
      );
  return ClinicalCase(
    id: j['id'] as String,
    patientId: j['id_paciente'] as String,
    status: _decode(caseStatusCodes, j['estado'], 'estado'),
    createdAt: parseDateTime(j['fecha_creacion']),
    foto1: image(ImageView.foto1),
    foto2: image(ImageView.foto2),
    clinicalData: clinicalDataFromJson(j['datos_clinicos'] as Json),
    prediction: j['prediccion'] == null ? null : predictionFromJson(j['prediccion'] as Json),
    suggestion: j['sugerencia_examenes'] as String?,
    analysisAttempts: j['intentos_analisis'] as int,
    internalNotes: [
      for (final n in j['notas_internas'] as List)
        InternalNote(
          text: (n as Json)['texto'] as String,
          authorName: n['autor_nombre'] as String,
          createdAt: parseDateTime(n['fecha']),
        ),
    ],
    lastError: j['ultimo_error'] as String?,
    overdueAlerted: j['alerta_vencido'] as bool? ?? false,
  );
}

// --- Validación clínica ---

ClinicalValidation validationFromJson(Json j) => ClinicalValidation(
      id: j['id'] as String,
      caseId: j['id_caso'] as String,
      especialistaNombre: j['especialista_nombre'] as String,
      cmp: j['numero_colegiatura'] as String,
      decision: _decode(decisionCodes, j['decision'], 'decision'),
      claseFinal: j['clase_final'] == null
          ? null
          : _decode(lesionClassCodes, j['clase_final'], 'clase_final'),
      sustentoClinico: j['sustento_clinico'] as String,
      fechaValidacion: parseDateTime(j['fecha_validacion']),
      prediccionOriginal: predictionFromJson(j['prediccion_original'] as Json),
      examenesAdicionales: j['examenes_adicionales'] as String?,
      sugerenciaTomada: j['sugerencia_tomada'] as bool?,
      complementaDe: j['complementa_de'] as String?,
    );

// --- Informes ---

CaseReport reportFromJson(Json j) => CaseReport(
      id: j['id'] as String,
      caseId: j['id_caso'] as String,
      conductaClinica: j['conducta_clinica'] as String,
      fechaCierre: parseDateTime(j['fecha_cierre']),
      validationId: j['id_validacion'] as String,
    );

/// `DocumentoInformeOut` no trae el id de la validación.
CaseReport reportFromDocumentJson(Json j) => CaseReport(
      id: j['id_informe'] as String,
      caseId: j['id_caso'] as String,
      conductaClinica: j['conducta_clinica'] as String,
      fechaCierre: parseDateTime(j['fecha_cierre']),
      validationId: '',
    );

ReportDocument reportDocumentFromJson(Json j,
        {String? foto1Path, String? foto2Path}) =>
    ReportDocument(
      caseId: j['id_caso'] as String,
      fechaCierre: parseDateTime(j['fecha_cierre']),
      pacienteNombre: j['paciente_nombres'] as String,
      historiaClinica: j['numero_historia_clinica'] as String,
      ubicacionLesion: j['ubicacion_lesion'] as String,
      conclusion: j['conclusion'] as String,
      conducta: j['conducta_clinica'] as String,
      especialistaNombre: j['especialista_nombre'] as String,
      cmp: j['numero_colegiatura'] as String,
      establecimiento: j['establecimiento'] as String,
      alcance: j['alcance'] as String,
      foto1Path: foto1Path,
      foto2Path: foto2Path,
      fechaNacimiento: j['fecha_nacimiento'] == null ? null : parseDate(j['fecha_nacimiento']),
      decision: j['decision'] as String?,
      sustentoClinico: j['sustento_clinico'] as String?,
      examenesAdicionales: j['examenes_adicionales'] as String?,
    );

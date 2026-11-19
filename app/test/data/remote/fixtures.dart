// Ejemplos de JSON con la forma de backend/dermavia/presentacion/esquemas.py.

Map<String, dynamic> userJson({
  String uid = 'especialista-dev',
  String rol = 'especialista',
  bool accesoClinico = true,
  String? aceptacion = '2026-11-19T14:00:00Z',
}) =>
    {
      'uid': uid,
      'rol': rol,
      'dni': '00000002',
      'nombres': 'Dra. Especialista Demo',
      'correo': 'especialista@dermavia.local',
      'estado': 'ACTIVO',
      'establecimiento': 'Hospital de demostración',
      'acceso_clinico': accesoClinico,
      'numero_colegiatura': '12345',
      'fecha_verificacion': '2026-11-19T13:00:00Z',
      'fecha_aceptacion_terminos': aceptacion,
      'requiere_aceptar_alcance': aceptacion == null,
    };

Map<String, dynamic> patientJson({String id = 'pac1', bool consent = true}) => {
      'id': id,
      'numero_historia_clinica': 'HC-001',
      'nombres': 'María Quispe Huamán',
      'fecha_nacimiento': '1970-05-02',
      'sexo': 'femenino',
      'fototipo': 'IV',
      'uid_medico_registro': 'especialista-dev',
      'fecha_registro': '2026-11-19T14:05:00.123456Z',
      'consentimiento': consent
          ? {
              'otorgado': true,
              'fecha_otorgamiento': '2026-11-19T14:06:00Z',
              'medico_nombre': 'Dra. Especialista Demo',
              'fecha_revocacion': null,
              'vigente': true,
            }
          : null,
      'consentimiento_vigente': consent,
    };

Map<String, dynamic> predictionJson({
  String clase = 'melanoma',
  double p = 0.0699,
  String banda = 'baja',
}) =>
    {
      'probabilidad_malignidad': p,
      'clase_predicha': clase,
      'linea_alerta': 0.06993006993006994,
      'banda': banda,
      'version_modelo': '20261004T172732Z_registro',
      'fecha_inferencia': '2026-11-19T14:10:00Z',
    };

Map<String, dynamic> caseJson({
  String id = 'a1b2c3d4e5f6a7b8c9d0',
  String estado = 'REGISTRADO',
  Map<String, dynamic>? prediccion,
  Map<String, String>? urls,
}) =>
    {
      'id': id,
      'id_paciente': 'pac1',
      'estado': estado,
      'datos_clinicos': {
        'ubicacion_lesion': 'Brazo derecho',
        'tiempo_aparicion': 'entre_3_y_12_meses',
        'sintomas': ['picor', 'cambio_color'],
      },
      'fecha_creacion': '2026-11-19T14:08:00Z',
      'vistas_cargadas': prediccion == null ? <String>[] : ['a', 'b'],
      'prediccion': prediccion,
      'sugerencia_examenes': prediccion == null ? null : 'Riesgo bajo, pero por encima…',
      'notas_internas': [
        {'texto': 'Revisar en 3 meses', 'autor_nombre': 'Dra. Demo', 'fecha': '2026-11-19T15:00:00Z'},
      ],
      'intentos_analisis': prediccion == null ? 0 : 1,
      'ultimo_error': null,
      'alerta_vencido': false,
      'urls_imagenes': urls,
    };

Map<String, dynamic> validationJson() => {
      'id': 'a1b2c3d4e5f6a7b8c9d0-principal',
      'id_caso': 'a1b2c3d4e5f6a7b8c9d0',
      'especialista_nombre': 'Dra. Especialista Demo',
      'numero_colegiatura': '12345',
      'decision': 'corregir',
      'clase_final': 'no_melanoma',
      'sustento_clinico': 'Patrón reticular regular.',
      'fecha_validacion': '2026-11-19T15:10:00Z',
      'examenes_adicionales': null,
      'sugerencia_tomada': false,
      'complementa_de': null,
      'prediccion_original': predictionJson(),
    };

Map<String, dynamic> reportDocumentJson() => {
      'id_informe': 'a1b2c3d4e5f6a7b8c9d0',
      'id_caso': 'a1b2c3d4e5f6a7b8c9d0',
      'fecha_cierre': '2026-11-19T15:20:00Z',
      'paciente_nombres': 'María Quispe Huamán',
      'numero_historia_clinica': 'HC-001',
      'fecha_nacimiento': '1970-05-02',
      'ubicacion_lesion': 'Brazo derecho',
      'conclusion': 'Lesión no compatible con melanoma.',
      'decision': 'corregir',
      'sustento_clinico': 'Patrón reticular regular.',
      'examenes_adicionales': null,
      'conducta_clinica': 'Control en 6 meses.',
      'especialista_nombre': 'Dra. Especialista Demo',
      'numero_colegiatura': '12345',
      'establecimiento': 'Hospital de demostración',
      'alcance': 'Herramienta de apoyo diagnóstico. No reemplaza el criterio médico…',
    };

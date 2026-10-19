enum Sex { femenino, masculino }

extension SexLabel on Sex {
  String get label => this == Sex.femenino ? 'Femenino' : 'Masculino';
  String get short => this == Sex.femenino ? 'F' : 'M';
}

/// Fototipo de piel según la escala de Fitzpatrick.
enum Phototype { i, ii, iii, iv, v, vi }

extension PhototypeLabel on Phototype {
  String get roman => const ['I', 'II', 'III', 'IV', 'V', 'VI'][index];
}

/// Consentimiento informado registrado por el médico (RF-02.6, RNF-06).
class Consent {
  const Consent({
    required this.otorgado,
    required this.fechaOtorgamiento,
    required this.uidMedico,
    required this.medicoNombre,
    this.fechaRevocacion,
  });

  final bool otorgado;
  final DateTime fechaOtorgamiento;
  final String uidMedico;
  final String medicoNombre;
  final DateTime? fechaRevocacion;

  bool get vigente => otorgado && fechaRevocacion == null;

  Consent revoked(DateTime at) => Consent(
        otorgado: otorgado,
        fechaOtorgamiento: fechaOtorgamiento,
        uidMedico: uidMedico,
        medicoNombre: medicoNombre,
        fechaRevocacion: at,
      );
}

/// Paciente atendido. No tiene cuenta ni credenciales (RF-02.5).
class Patient {
  const Patient({
    required this.id,
    required this.numeroHistoriaClinica,
    required this.nombres,
    required this.fechaNacimiento,
    required this.sexo,
    required this.fototipo,
    required this.uidMedicoRegistro,
    this.consent,
  });

  final String id;
  final String numeroHistoriaClinica;
  final String nombres;
  final DateTime fechaNacimiento;
  final Sex sexo;
  final Phototype fototipo;
  final String uidMedicoRegistro;
  final Consent? consent;

  bool get hasValidConsent => consent?.vigente ?? false;

  int ageAt(DateTime now) {
    var age = now.year - fechaNacimiento.year;
    final hadBirthday = now.month > fechaNacimiento.month ||
        (now.month == fechaNacimiento.month && now.day >= fechaNacimiento.day);
    if (!hadBirthday) age--;
    return age;
  }

  String get initials {
    final parts = nombres.split(' ').where((p) => p.isNotEmpty).toList();
    if (parts.length < 2) return parts.isEmpty ? '?' : parts.first[0];
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  /// Nombre corto para listas: "María Quispe H."
  String get shortName {
    final parts = nombres.split(' ').where((p) => p.isNotEmpty).toList();
    if (parts.length <= 2) return nombres;
    return '${parts[0]} ${parts[1]} ${parts[2][0]}.';
  }

  Patient copyWith({Consent? consent}) => Patient(
        id: id,
        numeroHistoriaClinica: numeroHistoriaClinica,
        nombres: nombres,
        fechaNacimiento: fechaNacimiento,
        sexo: sexo,
        fototipo: fototipo,
        uidMedicoRegistro: uidMedicoRegistro,
        consent: consent ?? this.consent,
      );
}

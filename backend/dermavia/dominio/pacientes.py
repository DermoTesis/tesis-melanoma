"""Módulo Pacientes: registro y búsqueda por historia clínica, y consentimiento informado.

El paciente no tiene credenciales. Sin un consentimiento vigente no se puede registrar un caso
(RF-02.6); `exigir_consentimiento` es la interfaz que usa Gestión de Casos para comprobarlo.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from .auditoria import ModuloAuditoria
from .errores import ConsentimientoRequerido, DatosInvalidos, NoEncontrado
from .modelos import Consentimiento, Fototipo, Paciente, Sexo, TipoEvento, Usuario
from .puertos import GeneradorIds, Reloj, RepoPacientes


def normalizar_hc(numero_historia_clinica: str) -> str:
    return "".join(numero_historia_clinica.split()).upper()


class ModuloPacientes:
    def __init__(self, pacientes: RepoPacientes, auditoria: ModuloAuditoria, reloj: Reloj,
                 generar_id: GeneradorIds):
        self._pacientes = pacientes
        self._auditoria = auditoria
        self._reloj = reloj
        self._generar_id = generar_id

    def registrar(self, medico: Usuario, *, numero_historia_clinica: str, nombres: str,
                  fecha_nacimiento: date, sexo: Sexo, fototipo: Fototipo) -> Paciente:
        hc, nombres = normalizar_hc(numero_historia_clinica), " ".join(nombres.split())
        if not hc:
            raise DatosInvalidos("Ingresa el número de historia clínica.")
        if not nombres:
            raise DatosInvalidos("Ingresa los nombres y apellidos del paciente.")
        hoy = self._reloj.ahora().date()
        if fecha_nacimiento > hoy or fecha_nacimiento.year < hoy.year - 120:
            raise DatosInvalidos("La fecha de nacimiento no es válida.")
        paciente = Paciente(
            id=self._generar_id(),
            numero_historia_clinica=hc,
            nombres=nombres,
            fecha_nacimiento=fecha_nacimiento,
            sexo=sexo,
            fototipo=fototipo,
            uid_medico_registro=medico.uid,
            fecha_registro=self._reloj.ahora(),
        )
        self._pacientes.crear(paciente)  # Conflicto si la historia clínica ya existe
        self._auditoria.registrar(TipoEvento.REGISTRO_PACIENTE, hc, medico)
        return paciente

    def buscar_por_hc(self, numero_historia_clinica: str) -> Paciente | None:
        return self._pacientes.buscar_por_hc(normalizar_hc(numero_historia_clinica))

    def obtener(self, id_paciente: str) -> Paciente:
        paciente = self._pacientes.obtener(id_paciente)
        if paciente is None:
            raise NoEncontrado("No se encontró al paciente.")
        return paciente

    def listar(self) -> list[Paciente]:
        return sorted(self._pacientes.listar(), key=lambda p: p.nombres)

    def registrar_consentimiento(self, medico: Usuario, id_paciente: str) -> Paciente:
        paciente = self.obtener(id_paciente)
        if paciente.consentimiento_vigente:
            return paciente
        paciente = replace(paciente, consentimiento=Consentimiento(
            otorgado=True,
            fecha_otorgamiento=self._reloj.ahora(),
            uid_medico=medico.uid,
            medico_nombre=medico.nombres,
        ))
        self._pacientes.guardar(paciente)
        self._auditoria.registrar(TipoEvento.CONSENTIMIENTO, paciente.numero_historia_clinica,
                                  medico)
        return paciente

    def revocar_consentimiento(self, medico: Usuario, id_paciente: str) -> Paciente:
        paciente = self.obtener(id_paciente)
        if not paciente.consentimiento_vigente:
            raise DatosInvalidos("El paciente no tiene un consentimiento vigente.")
        assert paciente.consentimiento is not None
        paciente = replace(paciente, consentimiento=replace(
            paciente.consentimiento, fecha_revocacion=self._reloj.ahora()))
        self._pacientes.guardar(paciente)
        self._auditoria.registrar(TipoEvento.REVOCACION_CONSENTIMIENTO,
                                  paciente.numero_historia_clinica, medico)
        return paciente

    def exigir_consentimiento(self, id_paciente: str) -> Paciente:
        paciente = self.obtener(id_paciente)
        if not paciente.consentimiento_vigente:
            raise ConsentimientoRequerido()
        return paciente

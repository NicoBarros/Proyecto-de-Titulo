import json
from datetime import timedelta

from django.contrib.messages import get_messages
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from inventario import privacidad, tareas
from inventario.models import Bloqueo, BusquedaIA, EventoSeguridad, Solicitud, SolicitudDerecho, Usuario

from .base import LeicaTestCase


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class AvisoPrivacidadTests(LeicaTestCase):

    @override_settings(PRIVACIDAD_CONTACTO='privacidad@inacap.cl', RETENCION_EVENTOS_DIAS=180)
    def test_es_publico_y_detalla_finalidad_plazos_y_derechos(self):
        r = self.client.get('/privacidad/')
        self.assertEqual(r.status_code, 200)
        for texto in ('Ley N.° 21.719', 'Base de licitud', '180 días', 'privacidad@inacap.cl', 'portabilidad',
                      'Google Gemini', 'Agencia de Protección de Datos Personales'):
            self.assertContains(r, texto)

    def test_tambien_se_ve_con_sesion_iniciada(self):
        self.client.force_login(self.docente)
        self.assertContains(self.client.get('/privacidad/'), 'aviso-privacidad')

    def test_enlazado_desde_el_login_y_el_pie(self):
        self.assertContains(self.client.get('/login/'), 'href="/privacidad/"', count=2)
        self.client.force_login(self.docente)
        r = self.client.get('/')
        self.assertContains(r, 'href="/privacidad/"')
        self.assertContains(r, 'href="/cuenta/mis-datos/"')


class MisDatosTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.estudiante)
        equipo = self.crear_equipo()
        self.solicitud = self.crear_solicitud(self.estudiante, equipos=[equipo])
        self.representada = self.crear_solicitud(self.docente, equipos=[self.crear_equipo('LTV-002')])
        Solicitud.objects.filter(id=self.representada.id).update(en_representacion_de=self.estudiante)
        Bloqueo.objects.create(usuario=self.estudiante, seccion='TIN-401', fecha_fin=timezone.now(), motivo='Atraso')
        BusquedaIA.objects.create(usuario=self.estudiante, consulta='osciloscopio', fuente='hibrida_local',
                                  resultados=1, util=True)
        EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.INICIO_SESION, usuario=self.estudiante,
                                       identificador=self.estudiante.email, ip='10.0.0.5')

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get('/cuenta/mis-datos/').status_code, 302)
        self.assertEqual(self.client.get('/cuenta/mis-datos/descargar/').status_code, 302)

    def test_muestra_perfil_y_resumen(self):
        r = self.client.get('/cuenta/mis-datos/')
        self.assertContains(r, self.estudiante.email)
        self.assertContains(r, 'TIN-401')
        self.assertEqual(r.context['resumen'], {'solicitudes': 2, 'bloqueos': 1, 'busquedas': 1, 'eventos': 2})

    def test_descarga_todos_sus_datos_en_json(self):
        r = self.client.get('/cuenta/mis-datos/descargar/')
        self.assertIn('attachment; filename="mis_datos_leica_', r['Content-Disposition'])
        datos = json.loads(r.content)
        self.assertEqual(datos['perfil']['correo'], self.estudiante.email)
        self.assertEqual(sorted(s['participacion'] for s in datos['solicitudes']), ['en representación', 'solicitante'])
        self.assertEqual(datos['solicitudes'][0]['items'][0]['tipo'], 'equipo')
        self.assertEqual(datos['bloqueos'][0]['seccion'], 'TIN-401')
        self.assertEqual(datos['busquedas'][0]['calificacion'], 'útil')
        self.assertEqual(datos['eventos_seguridad'][0]['ip'], '10.0.0.5')

    def test_no_incluye_datos_de_otras_personas(self):
        BusquedaIA.objects.create(usuario=self.docente, consulta='secreto del docente', fuente='hibrida_local')
        contenido = self.client.get('/cuenta/mis-datos/descargar/').content.decode()
        self.assertNotIn('secreto del docente', contenido)
        self.assertNotIn(self.docente.email, contenido)


class SolicitudDerechoTests(LeicaTestCase):

    def setUp(self):
        self.admin = self.crear_usuario('admin', Usuario.Rol.ENCARGADO_LABORATORIO, is_superuser=True, is_staff=True)
        self.client.force_login(self.estudiante)

    def solicitar(self, tipo='rectificacion', detalle='Mi apellido está mal escrito'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/cuenta/mis-datos/', {'tipo': tipo, 'detalle': detalle})

    def test_registra_la_solicitud_y_avisa_al_administrador(self):
        self.solicitar()
        solicitud = SolicitudDerecho.objects.get()
        self.assertEqual((solicitud.usuario, solicitud.identificador), (self.estudiante, self.estudiante.email))
        self.assertEqual(mail.outbox[0].to, [self.admin.email])
        self.assertIn('rectificación', mail.outbox[0].subject)
        self.assertIn(solicitud.vence.strftime('%d/%m/%Y'), mail.outbox[0].body)

    @override_settings(PLAZO_DERECHOS_DIAS=30)
    def test_plazo_y_vencimiento(self):
        self.solicitar()
        solicitud = SolicitudDerecho.objects.get()
        self.assertEqual(solicitud.vence, solicitud.creada + timedelta(days=30))
        self.assertFalse(solicitud.vencida)
        SolicitudDerecho.objects.update(creada=timezone.now() - timedelta(days=31))
        self.assertTrue(SolicitudDerecho.objects.get().vencida)

    def test_validaciones(self):
        for tipo, detalle, error in (
            ('otro', 'x', 'Selecciona un derecho válido.'),
            ('oposicion', '  ', 'Describe tu solicitud.'),
        ):
            self.assertIn(error, mensajes(self.solicitar(tipo, detalle)))
        self.solicitar('oposicion', 'No quiero que se registren mis búsquedas')
        self.assertIn('Ya tienes una solicitud pendiente de ese tipo.',
                      mensajes(self.solicitar('oposicion', 'Otra vez')))
        self.assertEqual(SolicitudDerecho.objects.count(), 1)

    def test_el_titular_ve_el_estado_y_la_respuesta(self):
        self.solicitar()
        SolicitudDerecho.objects.update(estado=SolicitudDerecho.Estado.ACEPTADA, respuesta='Apellido corregido')
        r = self.client.get('/cuenta/mis-datos/')
        self.assertContains(r, 'Apellido corregido')
        self.assertContains(r, 'derecho-aceptada')


class ResolucionDerechosTests(LeicaTestCase):

    def setUp(self):
        self.admin = self.crear_usuario('admin', Usuario.Rol.ENCARGADO_LABORATORIO, is_superuser=True, is_staff=True)
        self.client.force_login(self.admin)

    def derecho(self, tipo, usuario=None):
        usuario = usuario or self.estudiante
        return SolicitudDerecho.objects.create(usuario=usuario, identificador=usuario.email, tipo=tipo, detalle='x')

    def resolver(self, derecho, decision='aceptar', respuesta='Listo'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/panel-admin/', {
                'accion': 'resolver_derecho', 'derecho_id': derecho.id, 'decision': decision, 'respuesta': respuesta,
            })

    def test_panel_muestra_pendientes(self):
        self.derecho(SolicitudDerecho.Tipo.SUPRESION)
        r = self.client.get('/panel-admin/')
        self.assertContains(r, 'id="derechos"')
        self.assertContains(r, 'data-confirm-title="Suprimir datos"')

    def test_rectificacion_aceptada_notifica_al_titular(self):
        derecho = self.derecho(SolicitudDerecho.Tipo.RECTIFICACION)
        self.resolver(derecho, respuesta='Corregimos tu apellido')
        derecho.refresh_from_db()
        self.assertEqual((derecho.estado, derecho.resuelta_por), (SolicitudDerecho.Estado.ACEPTADA, self.admin))
        self.assertEqual(mail.outbox[0].to, [self.estudiante.email])
        self.assertIn('Corregimos tu apellido', mail.outbox[0].body)
        self.assertTrue(EventoSeguridad.objects.filter(detalle__contains='rectificación aceptada').exists())

    def test_rechazo(self):
        derecho = self.derecho(SolicitudDerecho.Tipo.OPOSICION)
        self.resolver(derecho, 'rechazar', 'El registro es necesario para la trazabilidad')
        derecho.refresh_from_db()
        self.assertEqual(derecho.estado, SolicitudDerecho.Estado.RECHAZADA)
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

    def test_bloqueo_aceptado_suspende_la_cuenta(self):
        self.resolver(self.derecho(SolicitudDerecho.Tipo.BLOQUEO))
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.is_active)

    def test_supresion_anonimiza_y_conserva_la_trazabilidad(self):
        equipo = self.crear_equipo()
        prestamo = self.crear_solicitud(self.estudiante, equipos=[equipo], estado=Solicitud.EstadoSolicitud.DEVUELTA)
        BusquedaIA.objects.create(usuario=self.estudiante, consulta='osciloscopio', fuente='hibrida_local')
        EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.INICIO_SESION, usuario=self.estudiante,
                                       identificador=self.estudiante.email, ip='10.0.0.5', agente='Firefox')
        EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.CAMBIO_CUENTA, usuario=self.admin,
                                       detalle=f'{self.estudiante.email}: rol cambiado')
        correo = self.estudiante.email
        derecho = self.derecho(SolicitudDerecho.Tipo.SUPRESION)
        self.resolver(derecho, respuesta='Datos suprimidos')
        self.estudiante.refresh_from_db()
        alias = f'anonimo-{self.estudiante.id}'
        self.assertEqual(self.estudiante.email, f'{alias}@anonimo.invalid')
        self.assertEqual(self.estudiante.get_full_name(), 'Titular anonimizado')
        self.assertIsNone(self.estudiante.seccion)
        self.assertFalse(self.estudiante.is_active or self.estudiante.has_usable_password())
        self.assertTrue(Solicitud.objects.filter(id=prestamo.id, solicitante=self.estudiante).exists())
        self.assertFalse(BusquedaIA.objects.filter(usuario=self.estudiante).exists())
        self.assertFalse(EventoSeguridad.objects.filter(identificador=correo).exists())
        self.assertFalse(EventoSeguridad.objects.filter(detalle__contains=correo).exists())
        self.assertTrue(EventoSeguridad.objects.filter(detalle=f'{alias}: rol cambiado').exists())
        derecho.refresh_from_db()
        self.assertEqual(derecho.identificador, alias)
        self.assertEqual(mail.outbox[0].to, [correo])
        self.assertIn('anonimizados', mail.outbox[0].body)

    def test_supresion_con_prestamo_en_curso_no_procede(self):
        self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.ENTREGADA)
        derecho = self.derecho(SolicitudDerecho.Tipo.SUPRESION)
        r = self.resolver(derecho)
        self.assertIn('préstamos en curso', ' '.join(mensajes(r)))
        derecho.refresh_from_db()
        self.assertEqual(derecho.estado, SolicitudDerecho.Estado.PENDIENTE)
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

    def test_validaciones(self):
        derecho = self.derecho(SolicitudDerecho.Tipo.RECTIFICACION)
        for datos, error in (
            ({'decision': 'tal vez'}, 'Decisión no válida.'),
            ({'respuesta': ' '}, 'Escribe la respuesta para el titular.'),
            ({'derecho_id': '9999'}, 'La solicitud no existe.'),
        ):
            r = self.client.post('/panel-admin/', {
                'accion': 'resolver_derecho', 'derecho_id': derecho.id, 'decision': 'aceptar',
                'respuesta': 'ok', **datos,
            })
            self.assertIn(error, mensajes(r))
        self.resolver(derecho)
        self.assertIn('La solicitud ya fue resuelta.', mensajes(self.resolver(derecho)))

    def test_solo_un_superusuario_resuelve(self):
        staff = self.crear_usuario('staff', Usuario.Rol.ENCARGADO_LABORATORIO, is_staff=True)
        self.client.force_login(staff)
        derecho = self.derecho(SolicitudDerecho.Tipo.SUPRESION)
        self.assertContains(self.client.get('/panel-admin/'), 'Pendiente de un superusuario')
        r = self.resolver(derecho)
        self.assertIn('Solo un superusuario puede resolver solicitudes de derechos.', mensajes(r))
        derecho.refresh_from_db()
        self.assertEqual(derecho.estado, SolicitudDerecho.Estado.PENDIENTE)

    def test_titular_ya_eliminado(self):
        derecho = SolicitudDerecho.objects.create(identificador='x@inacapmail.cl', tipo='supresion', detalle='x')
        self.resolver(derecho)
        derecho.refresh_from_db()
        self.assertEqual(derecho.estado, SolicitudDerecho.Estado.ACEPTADA)
        self.assertEqual(mail.outbox, [])


@override_settings(RETENCION_BUSQUEDAS_DIAS=365, RETENCION_EVENTOS_DIAS=180)
class RetencionTests(LeicaTestCase):

    def test_depura_segun_los_plazos_de_conservacion(self):
        vieja = BusquedaIA.objects.create(usuario=self.estudiante, consulta='a', fuente='hibrida_local')
        nueva = BusquedaIA.objects.create(usuario=self.estudiante, consulta='b', fuente='hibrida_local')
        BusquedaIA.objects.filter(id=vieja.id).update(fecha=timezone.now() - timedelta(days=366))
        evento_viejo = EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.INICIO_SESION, identificador='a')
        EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.INICIO_SESION, identificador='b')
        EventoSeguridad.objects.filter(id=evento_viejo.id).update(fecha=timezone.now() - timedelta(days=181))
        self.assertEqual(tareas.ejecutar()['datos_depurados'], {'busquedas_anonimizadas': 1, 'eventos_eliminados': 1})
        vieja.refresh_from_db()
        nueva.refresh_from_db()
        self.assertIsNone(vieja.usuario)
        self.assertEqual(nueva.usuario, self.estudiante)
        self.assertEqual(EventoSeguridad.objects.count(), 1)
        self.assertEqual(privacidad.depurar_datos_antiguos(), {'busquedas_anonimizadas': 0, 'eventos_eliminados': 0})

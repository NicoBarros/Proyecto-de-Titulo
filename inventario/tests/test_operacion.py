from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.utils import timezone

from inventario.models import Solicitud
from .base import LeicaTestCase


@override_settings(TAREAS_TOKEN='token-de-prueba')
class TareasProgramadasTests(LeicaTestCase):

    def crear_vencida(self):
        inicio = timezone.now() - timedelta(days=1)
        return self.crear_solicitud(self.estudiante, inicio=inicio, fin=inicio + timedelta(hours=1),
                                    estado=Solicitud.EstadoSolicitud.ENTREGADA)

    def test_con_token_marca_atrasadas(self):
        s = self.crear_vencida()
        r = self.client.post('/tareas/', HTTP_AUTHORIZATION='Bearer token-de-prueba')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['atrasadas_marcadas'], 1)
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ATRASADA)

    def test_sin_token_o_token_incorrecto_rechaza(self):
        s = self.crear_vencida()
        self.assertEqual(self.client.post('/tareas/').status_code, 401)
        self.assertEqual(self.client.post('/tareas/', HTTP_AUTHORIZATION='Bearer otro').status_code, 401)
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ENTREGADA)

    @override_settings(TAREAS_TOKEN='')
    def test_sin_token_configurado_queda_deshabilitado(self):
        self.assertEqual(self.client.post('/tareas/', HTTP_AUTHORIZATION='Bearer ').status_code, 401)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get('/tareas/', HTTP_AUTHORIZATION='Bearer token-de-prueba').status_code, 405)


class PaginacionTests(LeicaTestCase):

    def test_solicitudes_paginadas_conservan_filtros(self):
        for _ in range(25):
            self.crear_solicitud(self.estudiante)
        self.client.force_login(self.encargado)
        r = self.client.get('/solicitudes/')
        self.assertEqual(len(r.context['solicitudes']), 20)
        self.assertContains(r, '?page=2')
        r = self.client.get('/solicitudes/', {'page': 2})
        self.assertEqual(len(r.context['solicitudes']), 5)

    def test_panel_pagina_usuarios_y_equipos_por_separado(self):
        for i in range(30):
            self.crear_equipo(f'P-{i:03}')
        self.client.force_login(self.encargado)
        r = self.client.get('/panel-admin/', {'q_equipo': 'P-'})
        self.assertEqual(len(r.context['equipos_admin']), 25)
        self.assertContains(r, 'q_equipo=P-&amp;page_equipos=2')
        r = self.client.get('/panel-admin/', {'q_equipo': 'P-', 'page_equipos': 2})
        self.assertEqual(len(r.context['equipos_admin']), 5)


@override_settings(GEMINI_API_KEY='clave-falsa', IA_CONSULTAS_POR_HORA=2)
class LimiteIATests(LeicaTestCase):

    @patch('google.genai.Client')
    def test_supera_el_limite_y_usa_busqueda_local(self, client_cls):
        equipo = self.crear_equipo(nombre='Osciloscopio')
        client_cls.return_value.models.generate_content.return_value = MagicMock(text=f'[{equipo.id}]')
        self.client.force_login(self.estudiante)
        fuentes = [self.client.post('/busqueda/', {'consulta': 'osciloscopio'}).json()['fuente'] for _ in range(3)]
        self.assertEqual(fuentes, ['ia_gemini', 'ia_gemini', 'palabras_clave_local'])
        self.assertEqual(client_cls.return_value.models.generate_content.call_count, 2)

    @patch('google.genai.Client')
    def test_el_limite_es_por_usuario(self, client_cls):
        equipo = self.crear_equipo(nombre='Osciloscopio')
        client_cls.return_value.models.generate_content.return_value = MagicMock(text=f'[{equipo.id}]')
        self.client.force_login(self.estudiante)
        for _ in range(3):
            self.client.post('/busqueda/', {'consulta': 'osciloscopio'})
        self.client.force_login(self.docente)
        self.assertEqual(self.client.post('/busqueda/', {'consulta': 'osciloscopio'}).json()['fuente'], 'ia_gemini')

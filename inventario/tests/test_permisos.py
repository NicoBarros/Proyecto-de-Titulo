"""
Control de acceso: autenticacion y restricciones por rol (servidor, no solo UI).
"""
from inventario.models import Equipo
from .base import LeicaTestCase


URLS_PROTEGIDAS = [
    '/', '/inventario/', '/solicitudes/', '/mantenimiento/', '/reportes/',
    '/busqueda/', '/panel-admin/', '/inventario/exportar/',
]


class AutenticacionTests(LeicaTestCase):

    def test_anonimo_es_redirigido_al_login(self):
        for url in URLS_PROTEGIDAS:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r.url.startswith('/login/'), r.url)

    def test_login_con_email_y_password(self):
        r = self.client.post('/login/', {'username': 'estudiante@inacapmail.cl', 'password': 'Leica2026!'})
        self.assertRedirects(r, '/', fetch_redirect_response=False)

    def test_login_con_password_incorrecta(self):
        r = self.client.post('/login/', {'username': 'estudiante@inacapmail.cl', 'password': 'mala'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_usuario_inactivo_no_puede_entrar(self):
        self.estudiante.is_active = False
        self.estudiante.save()
        self.client.post('/login/', {'username': 'estudiante@inacapmail.cl', 'password': 'Leica2026!'})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout(self):
        self.client.force_login(self.estudiante)
        r = self.client.post('/logout/')
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)


class PermisosPorRolTests(LeicaTestCase):

    def assertAcceso(self, usuario, url, permitido):
        self.client.force_login(usuario)
        r = self.client.get(url)
        if permitido:
            self.assertEqual(r.status_code, 200, f'{usuario.rol} deberia acceder a {url}')
        else:
            self.assertIn(r.status_code, (302, 403), f'{usuario.rol} NO deberia acceder a {url}')

    def test_mantenimiento_solo_encargado_calidad_director(self):
        for u, ok in [(self.encargado, True), (self.calidad, True), (self.director, True),
                      (self.docente, False), (self.estudiante, False), (self.comite, False)]:
            with self.subTest(rol=u.rol):
                self.assertAcceso(u, '/mantenimiento/', ok)

    def test_importacion_csv_ya_no_existe(self):
        self.client.force_login(self.encargado)
        for url in ('/inventario/importar/', '/migracion/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_reportes_bloqueado_a_estudiantes_y_docentes(self):
        for u, ok in [(self.encargado, True), (self.calidad, True), (self.director, True),
                      (self.comite, True), (self.docente, False), (self.estudiante, False)]:
            with self.subTest(rol=u.rol):
                self.assertAcceso(u, '/reportes/', ok)

    def test_panel_admin_solo_staff(self):
        self.assertAcceso(self.encargado, '/panel-admin/', True)  # is_staff=True
        for u in (self.calidad, self.director, self.docente, self.estudiante):
            with self.subTest(rol=u.rol):
                self.assertAcceso(u, '/panel-admin/', False)

    def test_exportar_solo_encargado_y_calidad(self):
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get('/inventario/exportar/').status_code, 403)
        self.client.force_login(self.calidad)
        self.assertEqual(self.client.get('/inventario/exportar/').status_code, 200)

    def test_estudiante_no_puede_crear_equipo_por_post(self):
        self.client.force_login(self.estudiante)
        self.client.post('/inventario/?tab=equipos', {'codigo_inventario': 'HACK-1', 'nombre': 'x'})
        self.assertFalse(Equipo.objects.filter(codigo_inventario='HACK-1').exists())

    def test_estudiante_no_puede_editar_ni_eliminar_equipo(self):
        equipo = self.crear_equipo()
        self.client.force_login(self.estudiante)
        r = self.client.post(f'/inventario/equipo/{equipo.id}/editar/', {'codigo_inventario': 'LTV-001', 'nombre': 'Cambiado'})
        self.assertEqual(r.status_code, 403)
        r = self.client.post(f'/inventario/equipo/{equipo.id}/eliminar/')
        self.assertEqual(r.status_code, 403)
        equipo.refresh_from_db()
        self.assertEqual(equipo.nombre, 'Multimetro')

    def test_docente_sin_staff_no_puede_aprobar(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.client.force_login(self.docente)
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'pendiente')

    def test_estudiante_no_puede_aprobar_su_propia_solicitud(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.client.force_login(self.estudiante)
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'pendiente')

    def test_login_no_muestra_credenciales_fuera_de_debug(self):
        self.client.logout()
        self.assertNotContains(self.client.get('/login/'), 'Leica2026!')

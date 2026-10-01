// RF-11: buscar equipos describiendo en lenguaje natural lo que se
//        necesita, retornando los equipos relevantes disponibles.
// RNF-06: las capacidades de busqueda en lenguaje natural deben delegarse a
//        APIs externas (no se entrena ni aloja un modelo propio). Aqui se
//        integra con la API de Claude (Anthropic) como ejemplo: basta con
//        definir ANTHROPIC_API_KEY en .env. Si no hay API key configurada,
//        el endpoint cae a una busqueda por coincidencia de palabras clave
//        para que el prototipo funcione igual sin credenciales.
const express = require('express');
const db = require('../db/db');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

function busquedaPorPalabrasClave(consulta, disponibles) {
  const terminos = consulta.toLowerCase().split(/\s+/).filter(Boolean);
  return disponibles
    .map((e) => {
      const texto = `${e.nombre} ${e.modelo || ''} ${e.especificaciones || ''}`.toLowerCase();
      const score = terminos.reduce((acc, t) => acc + (texto.includes(t) ? 1 : 0), 0);
      return { ...e, score };
    })
    .filter((e) => e.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
}

async function busquedaConClaude(consulta, disponibles) {
  const catalogo = disponibles.map((e) => `- id=${e.id}: ${e.nombre} (${e.modelo || 's/modelo'}) - ${e.especificaciones || ''}`).join('\n');
  const prompt = `Eres un asistente que ayuda a un encargado de laboratorio a encontrar equipos.
Catalogo de equipos disponibles:
${catalogo}

Necesidad del usuario: "${consulta}"

Responde SOLO con un JSON array de los ids de equipo mas relevantes (maximo 5), ordenados del mas al menos relevante. Ejemplo: [3, 1, 7]`;

  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': process.env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 200,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  const data = await resp.json();
  const text = (data.content || []).map((b) => b.text || '').join('');
  const ids = JSON.parse(text.match(/\[[\d,\s]*\]/)?.[0] || '[]');
  return ids.map((id) => disponibles.find((e) => e.id === id)).filter(Boolean);
}

router.post('/', async (req, res) => {
  const { consulta } = req.body;
  if (!consulta) return res.status(400).json({ error: 'Falta "consulta".' });

  const disponibles = db.prepare(`SELECT * FROM equipos WHERE estado = 'disponible'`).all();

  if (process.env.ANTHROPIC_API_KEY) {
    try {
      const resultados = await busquedaConClaude(consulta, disponibles);
      return res.json({ fuente: 'ia_claude', resultados });
    } catch (err) {
      // si la API externa falla, no bloquear al usuario: caer a busqueda local
      console.error('Error llamando a la API de IA, usando fallback:', err.message);
    }
  }

  const resultados = busquedaPorPalabrasClave(consulta, disponibles);
  res.json({ fuente: 'palabras_clave_local (configura ANTHROPIC_API_KEY para busqueda semantica real)', resultados });
});

module.exports = router;

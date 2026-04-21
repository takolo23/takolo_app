"""
TAKOLO v4.0 — Bot WhatsApp FUNCIONAL + Deploy listo
====================================================
INSTALACIÓN LOCAL:
  pip install flask pandas openpyxl twilio werkzeug gunicorn

CORRER LOCAL:
  python takolo_v4.py
  → http://127.0.0.1:5100
  → admin@takolo.mx / takolo2025

DEPLOY EN RENDER.COM (GRATIS):
  1. Sube este archivo a GitHub como app.py
  2. Crea cuenta en render.com
  3. New → Web Service → conecta tu repo
  4. Build Command: pip install flask pandas openpyxl twilio werkzeug gunicorn
  5. Start Command: gunicorn app:app
  6. Environment Variables:
       TAKOLO_SECRET_KEY = (cualquier texto largo aleatorio)
  7. ¡Listo! Render te da URL pública gratis

SEGURIDAD — NUNCA pongas credenciales de Twilio en el código.
Configúralas desde el panel Bot WhatsApp una vez desplegado.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
from flask import (
    Flask, Response, flash, jsonify, redirect,
    render_template_string, request, send_file, session, url_for,
)
from jinja2 import DictLoader
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("takolo")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR        = Path(__file__).resolve().parent
APP_NAME        = "TAKOLO"
APP_VERSION     = "4.0"
DATA_DIR        = BASE_DIR / "takolo_data"
STORE_PATH      = DATA_DIR / "store.json"
USERS_PATH      = DATA_DIR / "users.json"
BOT_CFG_PATH    = DATA_DIR / "bot_config.json"
UPLOAD_DIR      = DATA_DIR / "uploads"
DOWNLOAD_DIR    = DATA_DIR / "downloads"
STAGING_DIR     = DATA_DIR / "staging"
LEGACY_DB       = BASE_DIR / "GestorIA_Data" / "core_vault.db"

ALLOWED_EXT   = {".xlsx", ".xls", ".csv"}
PAID_KW       = ["PAGADO","LIQUIDADO","FINALIZADO","CERO","LIQ"]

COLUMN_RULES: dict[str, list[str]] = {
    "id":        ["folio","id","credito","contrato","referencia","cuenta","num","no"],
    "nombre":    ["nombre","cliente","titular","deudor","nombre cliente","razon"],
    "telefono":  ["tel","cel","contacto","wa","whatsapp","movil","celular","telefono","fono","phone"],
    "ref_nombre":["ref nombre","referencia nombre","nombre referencia","contacto referencia","ref_nombre"],
    "ref_tel":   ["ref tel","referencia tel","tel referencia","contacto ref","ref_tel","referencia telefono"],
    "monto":     ["saldo","monto","deuda","vencido","total","adeudo","capital","importe"],
    "cuota":     ["cuota","mensualidad","pago semanal","pago quincenal","pago mensual","abono"],
    "status":    ["status","estado","situacion","estatus","etapa"],
    "gestor":    ["gestor","asignado","ejecutivo","operador","asesor","cobrador","responsable","agente"],
}

# ---------------------------------------------------------------------------
# Templates — Login
# ---------------------------------------------------------------------------
LOGIN_T = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TAKOLO — Acceso</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#09090f;--panel:rgba(255,255,255,0.04);--border:rgba(255,255,255,0.08);--primary:#4c98ff;--text:#f0f4ff;--muted:rgba(240,244,255,0.5);}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:grid;place-items:center;
  background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(76,152,255,0.15),transparent),radial-gradient(ellipse 60% 40% at 80% 80%,rgba(120,80,255,0.1),transparent);}
.card{width:100%;max-width:420px;padding:48px 40px;border-radius:32px;background:var(--panel);border:1px solid var(--border);backdrop-filter:blur(20px);}
.logo{font-family:'Syne',sans-serif;font-size:3rem;font-weight:800;background:linear-gradient(135deg,#4c98ff,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center;letter-spacing:-0.05em;}
.sub{text-align:center;color:var(--muted);font-size:0.88rem;margin:6px 0 36px;}
.err{background:rgba(204,74,92,0.15);border:1px solid rgba(204,74,92,0.3);color:#ff8895;padding:12px 16px;border-radius:14px;font-size:0.9rem;margin-bottom:20px;}
.info{background:rgba(76,152,255,0.1);border:1px solid rgba(76,152,255,0.25);color:#80c4ff;padding:12px 16px;border-radius:14px;font-size:0.9rem;margin-bottom:20px;}
.f{margin-bottom:16px;}
.f label{display:block;font-size:0.82rem;color:var(--muted);margin-bottom:8px;}
.f input{width:100%;padding:14px 16px;border-radius:14px;border:1px solid var(--border);background:rgba(255,255,255,0.05);color:var(--text);font:inherit;font-size:0.95rem;}
.f input:focus{outline:none;border-color:var(--primary);}
.btn{width:100%;padding:15px;border-radius:16px;border:0;background:linear-gradient(135deg,#4c98ff,#6366f1);color:#fff;font:inherit;font-size:1rem;font-weight:700;cursor:pointer;margin-top:8px;}
.div{display:flex;align-items:center;gap:12px;margin:20px 0;color:var(--muted);font-size:0.82rem;}
.div::before,.div::after{content:'';flex:1;height:1px;background:var(--border);}
.gbtn{width:100%;padding:14px;border-radius:16px;border:1px solid var(--border);background:rgba(255,255,255,0.05);color:var(--text);font:inherit;font-size:0.95rem;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px;text-decoration:none;}
.rl{text-align:center;margin-top:22px;color:var(--muted);font-size:0.88rem;}
.rl a{color:var(--primary);font-weight:600;}
.hint{margin-top:20px;padding:14px;border-radius:14px;background:rgba(76,152,255,0.08);border:1px solid rgba(76,152,255,0.2);font-size:0.82rem;color:rgba(200,220,255,0.8);}
.hint strong{color:var(--primary);}
</style></head><body>
<div class="card">
  <div class="logo">TAKOLO</div>
  <div class="sub">Sistema unificado de carteras v{{ version }}</div>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  {% if info  %}<div class="info">{{ info }}</div>{% endif %}
  <form method="post">
    <div class="f"><label>Correo electrónico</label><input type="email" name="email" placeholder="tu@empresa.com" required autocomplete="email"></div>
    <div class="f"><label>Contraseña</label><input type="password" name="password" placeholder="••••••••" required></div>
    <button type="submit" class="btn">Entrar al sistema</button>
  </form>
  <div class="div">o continúa con</div>
  <a href="/auth/google" class="gbtn">
    <svg width="20" height="20" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
    Continuar con Google
  </a>
  <div class="rl">¿Sin cuenta? <a href="/auth/register">Regístrate gratis</a></div>
  <div class="hint"><strong>Demo:</strong> admin@takolo.mx / takolo2025</div>
</div></body></html>"""

REGISTER_T = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TAKOLO — Registro</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#09090f;--panel:rgba(255,255,255,0.04);--border:rgba(255,255,255,0.08);--primary:#4c98ff;--text:#f0f4ff;--muted:rgba(240,244,255,0.5);}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:grid;place-items:center;padding:24px;background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(76,152,255,0.15),transparent);}
.card{width:100%;max-width:440px;padding:48px 40px;border-radius:32px;background:var(--panel);border:1px solid var(--border);}
.logo{font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;background:linear-gradient(135deg,#4c98ff,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px;}
h2{font-size:1rem;color:var(--muted);font-weight:400;margin-bottom:28px;}
.f{margin-bottom:14px;}
.f label{display:block;font-size:0.82rem;color:var(--muted);margin-bottom:6px;}
.f input,.f select{width:100%;padding:13px 16px;border-radius:13px;border:1px solid var(--border);background:rgba(255,255,255,0.05);color:var(--text);font:inherit;}
.f input:focus,.f select:focus{outline:none;border-color:var(--primary);}
.f select option{background:#1a1a2e;}
.btn{width:100%;padding:14px;border-radius:16px;border:0;background:linear-gradient(135deg,#4c98ff,#6366f1);color:#fff;font:inherit;font-size:1rem;font-weight:700;cursor:pointer;margin-top:8px;}
.ll{text-align:center;margin-top:18px;color:var(--muted);font-size:0.88rem;}
.ll a{color:var(--primary);font-weight:600;}
.err{background:rgba(204,74,92,0.15);border:1px solid rgba(204,74,92,0.3);color:#ff8895;padding:12px 16px;border-radius:14px;font-size:0.9rem;margin-bottom:16px;}
.ok{background:rgba(12,155,104,0.15);border:1px solid rgba(12,155,104,0.3);color:#4be080;padding:12px 16px;border-radius:14px;font-size:0.9rem;margin-bottom:16px;}
</style></head><body>
<div class="card">
  <div class="logo">TAKOLO</div><h2>Crea tu cuenta</h2>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  {% if success %}<div class="ok">{{ success }} <a href="/auth/login" style="color:#4be080;font-weight:700">→ Iniciar sesión</a></div>{% endif %}
  <form method="post">
    <div class="f"><label>Nombre completo</label><input type="text" name="name" placeholder="Juan Pérez" required></div>
    <div class="f"><label>Correo electrónico</label><input type="email" name="email" placeholder="tu@empresa.com" required></div>
    <div class="f"><label>Contraseña (mín. 8 caracteres)</label><input type="password" name="password" required minlength="8"></div>
    <div class="f"><label>Rol</label>
      <select name="role">
        <option value="gestor">Gestor de cobranza</option>
        <option value="supervisor">Supervisor</option>
        <option value="admin">Administrador</option>
      </select>
    </div>
    <button type="submit" class="btn">Crear cuenta</button>
  </form>
  <div class="ll">¿Ya tienes cuenta? <a href="/auth/login">Iniciar sesión</a></div>
</div></body></html>"""

TUTORIAL_T = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TAKOLO — Tutorial</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#09090f;--primary:#4c98ff;--text:#f0f4ff;--muted:rgba(240,244,255,0.55);--panel:rgba(255,255,255,0.04);--border:rgba(255,255,255,0.08);}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:grid;place-items:center;padding:24px;background-image:radial-gradient(ellipse 100% 60% at 50% 0%,rgba(76,152,255,0.12),transparent 60%);}
.shell{width:100%;max-width:680px;}
.hdr{text-align:center;margin-bottom:36px;}
.logo{font-family:'Syne',sans-serif;font-size:2.5rem;font-weight:800;background:linear-gradient(135deg,#4c98ff,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.pb{height:4px;background:rgba(255,255,255,0.08);border-radius:99px;margin-bottom:32px;overflow:hidden;}
.pf{height:100%;background:linear-gradient(90deg,#4c98ff,#a78bfa);border-radius:99px;transition:width 0.4s;}
.sc{display:none;padding:36px;border-radius:28px;background:var(--panel);border:1px solid var(--border);animation:fu 0.3s ease;}
.sc.active{display:block;}
@keyframes fu{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.si{font-size:2.8rem;margin-bottom:14px;display:block;}
.sn{display:inline-flex;padding:3px 12px;border-radius:99px;background:rgba(76,152,255,0.15);color:var(--primary);font-size:0.78rem;font-weight:700;margin-bottom:12px;}
.st{font-family:'Syne',sans-serif;font-size:1.75rem;font-weight:800;margin-bottom:10px;}
.sd{color:var(--muted);line-height:1.7;margin-bottom:20px;font-size:0.96rem;}
.tips{display:grid;gap:10px;margin-bottom:22px;}
.tip{display:flex;align-items:flex-start;gap:12px;padding:13px 15px;border-radius:15px;background:rgba(255,255,255,0.03);border:1px solid var(--border);}
.ti{font-size:1.15rem;flex-shrink:0;}.tt{font-size:0.89rem;color:rgba(240,244,255,0.8);line-height:1.5;}.tt strong{color:var(--text);}
.hint{padding:14px 18px;border-radius:16px;background:rgba(76,152,255,0.08);border:1px solid rgba(76,152,255,0.2);font-size:0.82rem;color:rgba(200,220,255,0.85);}
.hint code{color:#80c4ff;background:rgba(76,152,255,0.12);padding:2px 7px;border-radius:5px;}
.nav{display:flex;justify-content:space-between;align-items:center;margin-top:28px;}
.bn{display:inline-flex;align-items:center;gap:8px;padding:12px 22px;border-radius:14px;border:0;font:inherit;font-size:0.94rem;font-weight:700;cursor:pointer;transition:transform 0.18s;}
.bn:hover{transform:translateY(-1px);}
.bp{background:rgba(255,255,255,0.06);color:var(--muted);}
.bx{background:linear-gradient(135deg,#4c98ff,#6366f1);color:#fff;}
.bf{background:linear-gradient(135deg,#0c9b68,#4be080);color:#0f2a1a;}
.dots{display:flex;gap:8px;}
.dot{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.15);cursor:pointer;transition:background 0.2s,transform 0.2s;}
.dot.active{background:var(--primary);transform:scale(1.3);}
.skip{display:block;text-align:center;margin-top:16px;color:var(--muted);font-size:0.84rem;}
.skip a{color:var(--primary);}
</style></head><body>
<div class="shell">
  <div class="hdr"><div class="logo">TAKOLO</div><p style="color:var(--muted);margin-top:8px">Bienvenido/a — 5 pasos rápidos</p></div>
  <div class="pb"><div class="pf" id="pbar" style="width:20%"></div></div>
  <div class="sc active" data-step="1">
    <span class="si">👋</span><span class="sn">Paso 1 de 5</span>
    <h2 class="st">¡Bienvenido a TAKOLO!</h2>
    <p class="sd">Tu centro de operaciones para cobranza. Sube carteras, contacta deudores y sus referencias, y supervisa tu equipo.</p>
    <div class="tips">
      <div class="tip"><span class="ti">📁</span><div class="tt"><strong>Sube Excel o CSV</strong> — TAKOLO detecta columnas automáticamente.</div></div>
      <div class="tip"><span class="ti">📱</span><div class="tt"><strong>Mensajes a deudores Y referencias</strong> — el bot contacta al cliente y a su referencia si no contesta.</div></div>
      <div class="tip"><span class="ti">👥</span><div class="tt"><strong>Multi-gestor</strong> — asigna carteras y supervisa avance en tiempo real.</div></div>
    </div>
  </div>
  <div class="sc" data-step="2">
    <span class="si">📊</span><span class="sn">Paso 2 de 5</span>
    <h2 class="st">Procesa tu primera cartera</h2>
    <p class="sd">Ve a <strong>Procesar Cartera</strong>. Solo 3 pasos:</p>
    <div class="tips">
      <div class="tip"><span class="ti">1️⃣</span><div class="tt"><strong>Sube tu archivo</strong> — .xlsx, .xls o .csv.</div></div>
      <div class="tip"><span class="ti">2️⃣</span><div class="tt"><strong>Elige gestor</strong> — TODOS o filtra por ejecutivo.</div></div>
      <div class="tip"><span class="ti">3️⃣</span><div class="tt"><strong>Descarga y gestiona</strong> — Excel limpio + acceso inmediato.</div></div>
    </div>
    <div class="hint">💡 TAKOLO reconoce columnas como <code>SALDO</code>, <code>CLIENTE</code>, <code>TEL</code>, <code>REF TEL</code>, <code>GESTOR</code>.</div>
  </div>
  <div class="sc" data-step="3">
    <span class="si">💬</span><span class="sn">Paso 3 de 5</span>
    <h2 class="st">Gestiona clientes</h2>
    <div class="tips">
      <div class="tip"><span class="ti">📞</span><div class="tt"><strong>Llama o envía WhatsApp</strong> al deudor con un clic.</div></div>
      <div class="tip"><span class="ti">👨‍👩‍👧</span><div class="tt"><strong>Contacta la referencia</strong> — si el deudor no contesta, un botón envía mensaje a su referencia.</div></div>
      <div class="tip"><span class="ti">💰</span><div class="tt"><strong>Marca como pagado</strong> — se archiva automáticamente.</div></div>
    </div>
  </div>
  <div class="sc" data-step="4">
    <span class="si">🤖</span><span class="sn">Paso 4 de 5</span>
    <h2 class="st">Bot WhatsApp</h2>
    <div class="tips">
      <div class="tip"><span class="ti">⚙️</span><div class="tt"><strong>Configura Twilio</strong> — sandbox gratis en twilio.com.</div></div>
      <div class="tip"><span class="ti">👥</span><div class="tt"><strong>Envía a deudores Y referencias</strong> — el bot manda mensajes personalizados a ambos en una campaña.</div></div>
      <div class="tip"><span class="ti">📤</span><div class="tt"><strong>Envío por lotes</strong> — controla cuántos mensajes y el intervalo.</div></div>
    </div>
    <div class="hint">⚡ Sin Twilio: copia mensajes desde "Mensajes Auto" y envía desde tu WhatsApp personal.</div>
  </div>
  <div class="sc" data-step="5">
    <span class="si">📈</span><span class="sn">Paso 5 de 5</span>
    <h2 class="st">Supervisa tu equipo</h2>
    <div class="tips">
      <div class="tip"><span class="ti">👁️</span><div class="tt"><strong>Gestores en vivo</strong> — contactados hoy vs pendientes.</div></div>
      <div class="tip"><span class="ti">📊</span><div class="tt"><strong>WAPES MATRIX</strong> — resumen financiero por gestor.</div></div>
    </div>
    <div class="hint">🎉 <strong>¡Listo!</strong> Pulsa <strong>"Comenzar"</strong> para ir al Dashboard.</div>
  </div>
  <div class="nav">
    <button class="bn bp" id="btnPrev" onclick="prevStep()" style="display:none">← Anterior</button>
    <div class="dots" id="dots"></div>
    <button class="bn bx" id="btnNext" onclick="nextStep()">Siguiente →</button>
  </div>
  <div class="skip"><a href="/dashboard">Saltar tutorial →</a></div>
</div>
<script>
let cur=1,tot=5;
function render(){
  document.getElementById('pbar').style.width=(cur/tot*100)+'%';
  document.getElementById('btnPrev').style.display=cur>1?'inline-flex':'none';
  const b=document.getElementById('btnNext');
  if(cur===tot){b.textContent='🚀 Comenzar';b.className='bn bf';b.onclick=()=>location.href='/dashboard';}
  else{b.textContent='Siguiente →';b.className='bn bx';b.onclick=nextStep;}
  const dc=document.getElementById('dots');dc.innerHTML='';
  for(let i=1;i<=tot;i++){const d=document.createElement('div');d.className='dot'+(i===cur?' active':'');d.onclick=()=>goTo(i);dc.appendChild(d);}
}
function goTo(n){document.querySelectorAll('.sc').forEach(e=>e.classList.remove('active'));document.querySelector('[data-step="'+n+'"]').classList.add('active');cur=n;render();}
function nextStep(){if(cur<tot)goTo(cur+1);}
function prevStep(){if(cur>1)goTo(cur-1);}
render();
</script></body></html>"""

# ---------------------------------------------------------------------------
# BASE + PAGES CSS
# ---------------------------------------------------------------------------
CSS = """:root{--bg:#eef3fb;--panel:#fff;--panel-soft:#f8fbff;--line:#d7e0f0;--line-soft:#e7edf8;--text:#162447;--muted:#6f7f9d;--primary:#27439a;--accent:#4f7cff;--success:#0c9b68;--warning:#d6871f;--danger:#cc4a5c;--shadow:0 18px 40px rgba(21,48,102,0.08);}
*{box-sizing:border-box;}body{margin:0;font-family:'DM Sans','Segoe UI',sans-serif;color:var(--text);background:linear-gradient(180deg,#f5f8fe,#edf3fb);}
a{color:inherit;text-decoration:none;}code{padding:2px 7px;border-radius:999px;background:rgba(39,67,154,0.08);color:#183472;}
.app-shell{display:grid;grid-template-columns:256px minmax(0,1fr);min-height:100vh;}
.sidebar{display:flex;flex-direction:column;gap:18px;padding:28px 18px;background:rgba(255,255,255,0.9);border-right:1px solid rgba(39,67,154,0.08);}
.brand-block{padding:10px 12px 20px;border-bottom:1px solid var(--line-soft);}
.brand-name{font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;letter-spacing:-0.05em;color:var(--primary);}
.brand-sub{margin-top:4px;color:var(--muted);font-size:0.78rem;text-transform:uppercase;letter-spacing:0.08em;}
.sidebar-nav{display:flex;flex-direction:column;gap:10px;}
.nav-link{display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:18px;color:var(--text);transition:transform .18s,background .18s;}
.nav-link:hover{transform:translateX(4px);background:rgba(39,67,154,0.06);}
.nav-link.active{color:#fff;background:linear-gradient(135deg,var(--primary),var(--accent));box-shadow:0 14px 32px rgba(39,67,154,0.22);}
.nav-icon{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:12px;background:rgba(255,255,255,0.16);font-size:0.72rem;font-weight:700;}
.sidebar-footer{margin-top:auto;padding:16px 12px 0;border-top:1px solid var(--line-soft);color:var(--muted);font-size:0.82rem;}
.user-chip{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:14px;background:rgba(39,67,154,0.06);margin-bottom:10px;}
.user-av{width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,var(--primary),var(--accent));color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;}
.user-name{font-weight:700;font-size:0.88rem;color:var(--text);}.user-role{font-size:0.75rem;color:var(--muted);text-transform:capitalize;}
.logout-link{color:var(--danger);font-size:0.82rem;font-weight:600;}
.main-panel{padding:28px;}
.flash-stack{display:grid;gap:10px;margin-bottom:18px;}
.flash{padding:14px 18px;border-radius:16px;font-weight:600;}
.flash-success{background:rgba(12,155,104,0.12);color:#086545;}
.flash-error{background:rgba(204,74,92,0.12);color:#8a2332;}
.flash-info{background:rgba(79,124,255,0.12);color:#23408c;}
.page-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:22px;}
.page-head h1{margin:0;font-family:'Syne',sans-serif;font-size:clamp(2rem,4vw,3rem);line-height:1;letter-spacing:-0.06em;}
.page-head p,.section-head p{margin:8px 0 0;color:var(--muted);}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-bottom:22px;}
.metric-card{padding:24px;border-radius:20px;background:var(--panel);border:1px solid var(--line-soft);box-shadow:var(--shadow);}
.metric-card.success{background:linear-gradient(180deg,#fff,#f2fbf7);}
.metric-card.warning{background:linear-gradient(180deg,#fff,#fff9ef);}
.metric-card.accent{background:linear-gradient(180deg,#fff,#f1f5ff);}
.metric-card.small{padding:20px;}
.metric-label{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;font-weight:700;}
.metric-value{margin-top:10px;font-size:clamp(1.7rem,2.8vw,2.6rem);font-weight:800;letter-spacing:-.06em;}
.metric-note{margin-top:8px;color:var(--muted);font-size:.92rem;}
.content-card{margin-bottom:22px;padding:24px;border-radius:28px;background:rgba(255,255,255,0.92);border:1px solid rgba(39,67,154,0.08);box-shadow:var(--shadow);}
.success-card{background:linear-gradient(180deg,#fff,#f5fcf8);}
.section-head{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:18px;}
.section-head h2{margin:0;font-size:1.45rem;letter-spacing:-.04em;}
.ghost-link{color:var(--primary);font-weight:700;}
.table-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;}
th,td{padding:16px 14px;text-align:left;border-bottom:1px solid var(--line-soft);font-size:.95rem;}
thead th{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;}
tbody tr:hover{background:rgba(39,67,154,0.04);}
.money-cell{color:var(--success);font-weight:700;}
.status-pill{display:inline-flex;align-items:center;padding:7px 12px;border-radius:999px;font-size:.82rem;font-weight:700;}
.status-pill.ok{color:#0a6a49;background:rgba(12,155,104,0.14);}
.status-pill.bad{color:#92293b;background:rgba(204,74,92,0.14);}
.empty-state{padding:30px;border:1px dashed var(--line);border-radius:22px;background:var(--panel-soft);}
.empty-state h3{margin:0 0 8px;}.empty-state p{margin:0;color:var(--muted);}
.delete-btn,.file-delete-x{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:8px;border:0;cursor:pointer;background:rgba(204,74,92,0.1);color:var(--danger);font-weight:700;font-size:0.85rem;transition:background .18s,transform .18s;}
.delete-btn:hover,.file-delete-x:hover{background:rgba(204,74,92,0.25);transform:scale(1.1);}
.file-delete-x{width:22px;height:22px;font-size:0.75rem;margin-left:-4px;margin-right:4px;}
.stepper{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;}
.step{display:flex;align-items:center;gap:14px;padding:16px 18px;border-radius:20px;color:var(--muted);background:#f4f7fd;border:1px solid transparent;}
.step.active{color:#183472;background:linear-gradient(180deg,#f7f9ff,#eef4ff);border-color:rgba(39,67,154,0.12);}
.step.done{color:var(--primary);background:rgba(39,67,154,0.08);}
.step-index{display:inline-flex;align-items:center;justify-content:center;width:42px;height:42px;border-radius:14px;background:#dce6fb;color:var(--primary);font-weight:800;}
.step.active .step-index,.step.done .step-index{background:linear-gradient(135deg,var(--primary),var(--accent));color:#fff;}
.step strong,.step small{display:block;}.step small{margin-top:4px;}
.upload-layout{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(320px,.85fr);gap:22px;align-items:start;}
.upload-form,.stack-form{display:grid;gap:16px;}
.upload-zone{display:grid;place-items:center;gap:8px;min-height:280px;padding:26px;border-radius:26px;border:2px dashed #cdd9f2;background:linear-gradient(180deg,#fcfdff,#f6f9ff);text-align:center;cursor:pointer;}
.upload-zone input{display:none;}
.upload-title{font-size:1.5rem;font-weight:800;letter-spacing:-.04em;}
.upload-subtitle,.upload-caption{color:var(--muted);}
.field-label{font-size:.9rem;color:var(--muted);font-weight:700;}
.field-control{width:100%;padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--text);font:inherit;}
.primary-btn,.secondary-btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;padding:14px 18px;border:0;border-radius:16px;cursor:pointer;font:inherit;font-weight:700;transition:transform .18s;}
.primary-btn:hover,.secondary-btn:hover{transform:translateY(-1px);}
.primary-btn{color:#fff;background:linear-gradient(135deg,var(--primary),var(--accent));box-shadow:0 18px 34px rgba(39,67,154,.24);}
.secondary-btn{color:var(--primary);background:rgba(39,67,154,.08);}
.inline-btn{white-space:nowrap;}
.gestores-detected{margin:16px 0;padding:14px;border-radius:16px;background:rgba(39,67,154,0.05);border:1px solid rgba(39,67,154,0.12);}
.gestores-label{font-size:.82rem;color:var(--muted);font-weight:700;margin-bottom:10px;text-transform:uppercase;letter-spacing:.08em;}
.gestores-chips{display:flex;flex-wrap:wrap;gap:8px;}
.gestor-chip{display:inline-flex;padding:6px 14px;border-radius:999px;background:rgba(39,67,154,.1);color:var(--primary);font-weight:700;font-size:.82rem;border:1px solid rgba(79,124,255,.2);}
.bot-config-form,.launch-form{display:grid;gap:20px;}
.config-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;}
.field-group label{display:block;font-size:.82rem;color:var(--muted);font-weight:700;margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em;}
.field-group input,.field-group select{width:100%;padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--text);font:inherit;font-size:.95rem;}
.msg-preview-box{padding:18px;border-radius:18px;background:#f0f7ff;border:1px solid rgba(79,124,255,.2);}
.msg-preview-label{font-size:.78rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;}
.msg-preview-text{white-space:pre-wrap;font-size:.9rem;color:var(--text);line-height:1.6;}
.instructions-grid{display:grid;gap:14px;}
.instruction-step{display:flex;align-items:flex-start;gap:16px;padding:16px;border-radius:18px;background:rgba(39,67,154,.04);border:1px solid var(--line-soft);}
.inst-num{display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:14px;background:linear-gradient(135deg,var(--primary),var(--accent));color:#fff;font-weight:800;flex-shrink:0;}
.instruction-step strong{display:block;margin-bottom:4px;}.instruction-step p{margin:0;color:var(--muted);font-size:.9rem;}
.ops-tabs{display:flex;gap:4px;margin-bottom:18px;border-bottom:2px solid var(--line-soft);}
.ops-tab{padding:12px 20px;font-weight:700;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px;}
.ops-tab:hover{color:var(--primary);}.ops-tab.active{color:var(--primary);border-bottom-color:var(--primary);}
.ops-hero{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:22px;}
.ops-kicker{display:inline-flex;padding:8px 12px;border-radius:999px;background:rgba(39,67,154,.12);color:var(--primary);font-weight:700;font-size:.82rem;}
.ops-shell{padding:22px;border-radius:32px;background:linear-gradient(180deg,#111214,#090909);color:#f5f7fb;box-shadow:0 22px 50px rgba(0,0,0,.26);}
.ops-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:18px;}
.ops-metric{padding:18px;border-radius:22px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.05);}
.ops-metric span,.ops-metric small{color:rgba(236,241,255,.7);}
.ops-metric strong{display:block;margin-top:8px;font-size:2rem;letter-spacing:-.05em;}
.ops-metric.blue strong{color:#66a7ff;}.ops-metric.coral strong{color:#ff6d72;}.ops-metric.green strong{color:#4be080;}.ops-metric.gold strong{color:#ffd34f;}
.ops-controls{display:grid;gap:14px;margin-bottom:20px;}
.ops-search-form{display:grid;grid-template-columns:1fr 160px auto;gap:12px;}
.ops-search-form input,.ops-search-form select{width:100%;padding:13px 15px;border-radius:15px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);color:#f5f7fb;font:inherit;}
.ops-segments,.ops-chip-row{display:flex;flex-wrap:wrap;gap:10px;}
.ops-pill,.ops-chip{display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;background:rgba(255,255,255,.05);color:rgba(245,247,251,.78);border:1px solid rgba(255,255,255,.06);font-weight:700;}
.ops-pill.active,.ops-chip.active{background:linear-gradient(135deg,#4c98ff,#5e79ff);color:#fff;}
.ops-main-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(340px,.8fr);gap:18px;}
.ops-column{min-width:0;}
.ops-section-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;}
.ops-section-head h2,.ops-detail-head h2{margin:0;font-size:1.45rem;letter-spacing:-.04em;}
.ops-list{display:grid;gap:12px;}
.ops-client-card,.ops-detail-card{border-radius:24px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.06);}
.ops-client-card{display:grid;grid-template-columns:54px minmax(0,1fr) auto;gap:14px;align-items:center;padding:16px;transition:transform .18s,border-color .18s;}
.ops-client-card:hover,.ops-client-card.selected{transform:translateY(-1px);border-color:rgba(102,167,255,.55);}
.ops-avatar{display:inline-flex;align-items:center;justify-content:center;width:54px;height:54px;border-radius:18px;background:rgba(76,152,255,.14);color:#66a7ff;font-weight:800;font-size:1.25rem;}
.ops-avatar.small{width:40px;height:40px;font-size:1rem;border-radius:12px;flex-shrink:0;}
.ops-client-body,.ops-client-money{display:grid;gap:4px;}
.ops-client-body strong,.ops-client-money strong{color:#f7fbff;}
.ops-client-body span,.ops-client-money em,.ops-client-money small{color:rgba(236,241,255,.7);}
.ops-client-money{text-align:right;}.ops-client-money strong{color:#ff7a7f;font-size:1.1rem;}
.ops-detail-column{display:grid;gap:16px;align-content:start;}
.ops-detail-card{padding:18px;}
.ops-detail-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:16px;}
.ops-detail-head p{margin:6px 0 0;color:rgba(236,241,255,.7);}
.ops-detail-label,.ops-info-list span{color:rgba(236,241,255,.7);}
.ops-amount-panel{display:grid;gap:14px;margin-bottom:16px;}
.ops-amount-big{padding:18px;border-radius:22px;background:rgba(255,109,114,.12);border:1px solid rgba(255,109,114,.32);}
.ops-amount-big span{display:block;color:rgba(255,230,231,.75);}
.ops-amount-big strong{display:block;margin-top:10px;color:#ff7a7f;font-size:2.05rem;letter-spacing:-.05em;}
.ops-amount-split{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}
.ops-amount-split div{padding:16px;border-radius:18px;background:rgba(255,255,255,.04);}
.ops-amount-split span{display:block;color:rgba(236,241,255,.7);}
.ops-amount-split strong{display:block;margin-top:8px;}
.ops-actions{display:grid;gap:10px;margin-bottom:12px;}
.ops-action{display:inline-flex;align-items:center;justify-content:center;min-height:50px;border-radius:18px;font-weight:800;border:0;cursor:pointer;font:inherit;color:#fff;}
.ops-action.blue{background:#4c98ff;}.ops-action.green{background:#20d266;}.ops-action.lime{background:#65db5c;color:#0f2511;}.ops-action.gold-action{background:#c8890a;}.ops-action.red-action{background:rgba(204,74,92,.85);}
.ops-action.ref-action{background:linear-gradient(135deg,#7c3aed,#a855f7);font-size:0.82rem;}
.ref-box{margin-top:12px;padding:14px;border-radius:18px;background:rgba(124,58,237,0.1);border:1px solid rgba(168,85,247,0.25);}
.ref-box-title{font-size:0.78rem;color:rgba(200,180,255,0.8);font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;}
.ref-row{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px;}
.ref-row span{color:rgba(236,241,255,.7);font-size:0.88rem;}
.ref-row strong{color:#f0e6ff;font-size:0.9rem;}
.ops-info-list{display:grid;gap:10px;}
.ops-info-list div{display:flex;justify-content:space-between;gap:12px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06);}
.ops-info-list strong{color:#f7fbff;}
.ops-empty{padding:28px 20px;border-radius:22px;text-align:center;background:rgba(255,255,255,.03);border:1px dashed rgba(255,255,255,.12);}
.ops-empty h3{margin:0 0 8px;}.ops-empty p{margin:0;color:rgba(236,241,255,.66);}
.ops-empty.detail{min-height:360px;display:grid;place-content:center;}
.file-selector-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:16px;padding:12px 16px;border-radius:18px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.07);}
.file-selector-label{font-size:.82rem;color:rgba(236,241,255,.6);font-weight:700;margin-right:4px;}
.ops-client-card.contactado{border-color:rgba(75,224,128,.4);}.ops-client-card.inactivo{opacity:.55;}
.tag-contactado{display:inline-flex;padding:3px 8px;border-radius:999px;background:rgba(75,224,128,.18);color:#4be080;font-size:.72rem;font-weight:700;}
.danger-pill{background:rgba(204,74,92,.18);color:#ff8895;border:1px solid rgba(204,74,92,.3);cursor:pointer;font:inherit;font-weight:700;}
.msg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;}
.msg-card{border-radius:22px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08);padding:18px;display:flex;flex-direction:column;gap:14px;}
.msg-card-head{display:flex;align-items:center;gap:12px;}
.msg-card-head > div:nth-child(2){flex:1;}
.msg-card-head strong{display:block;color:#f7fbff;font-size:.95rem;}
.msg-card-head span{font-size:.82rem;color:rgba(236,241,255,.6);}
.msg-amounts{display:flex;flex-direction:column;align-items:flex-end;font-size:.82rem;color:rgba(236,241,255,.7);}
.msg-amounts b{color:#ff7a7f;}
.msg-body{white-space:pre-wrap;line-height:1.6;font-size:.9rem;padding:14px;border-radius:16px;background:rgba(255,255,255,.04);color:#f7fbff;flex:1;}
.msg-actions{display:flex;gap:8px;flex-wrap:wrap;}
.msg-btn{display:inline-flex;align-items:center;justify-content:center;padding:9px 14px;border-radius:14px;font-weight:700;font-size:.84rem;border:0;cursor:pointer;font:inherit;flex:1;}
.msg-btn.green{background:#20d266;color:#fff;}.msg-btn.gray{background:rgba(255,255,255,.08);color:rgba(245,247,251,.85);}
.msg-btn.purple{background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;}
.campaign-badge{display:inline-flex;padding:4px 10px;border-radius:999px;font-size:0.75rem;font-weight:700;}
.badge-ok{background:rgba(12,155,104,0.2);color:#4be080;}.badge-err{background:rgba(204,74,92,0.2);color:#ff8895;}.badge-prev{background:rgba(79,124,255,0.2);color:#80c4ff;}
#tk-toast{position:fixed;bottom:28px;right:28px;z-index:9999;padding:14px 20px;border-radius:16px;background:#1d2235;color:#f7fbff;font-weight:700;font-size:.9rem;box-shadow:0 8px 32px rgba(0,0,0,.4);opacity:0;transform:translateY(8px);transition:opacity .22s,transform .22s;pointer-events:none;}
#tk-toast.toast-visible{opacity:1;transform:translateY(0);}
#tk-toast.toast-error{background:#5a1c24;color:#ff8895;}
.deploy-card{padding:20px;border-radius:20px;background:linear-gradient(135deg,rgba(12,155,104,0.08),rgba(79,124,255,0.08));border:1px solid rgba(79,124,255,0.2);margin-bottom:16px;}
.deploy-card h3{margin:0 0 10px;font-size:1rem;color:var(--primary);}
.deploy-card pre{margin:10px 0 0;padding:12px;border-radius:12px;background:rgba(0,0,0,0.05);font-size:0.82rem;overflow-x:auto;color:var(--text);}
@media(max-width:1180px){.metric-grid,.upload-layout{grid-template-columns:repeat(2,minmax(0,1fr));}.ops-summary-grid,.ops-main-grid{grid-template-columns:1fr;}.config-grid{grid-template-columns:1fr;}}
@media(max-width:900px){.app-shell{grid-template-columns:1fr;}.sidebar{border-right:0;border-bottom:1px solid rgba(39,67,154,.08);}.metric-grid,.upload-layout,.stepper{grid-template-columns:1fr;}.msg-grid{grid-template-columns:1fr;}}
@media(max-width:640px){.main-panel{padding:18px;}.content-card,.metric-card{padding:18px;}th,td{padding:14px 10px;}}"""

JS = """document.addEventListener("DOMContentLoaded",()=>{
  const fi=document.querySelector("#cartera_file"),lb=document.querySelector("[data-file-label]");
  if(fi&&lb)fi.addEventListener("change",()=>{lb.textContent=fi.files.length?"✓ "+fi.files[0].name:"Formatos: .xlsx, .xls, .csv";});
});"""

# ---------------------------------------------------------------------------
# BASE TEMPLATE
# ---------------------------------------------------------------------------
BASE_T = """<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}TAKOLO{% endblock %}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ url_for('styles_asset') }}">
</head><body>
<div class="app-shell">
  <aside class="sidebar">
    <div class="brand-block">
      <div class="brand-name">TAKOLO</div>
      <div class="brand-sub">Sistema unificado v4</div>
    </div>
    <nav class="sidebar-nav">
      <a class="nav-link {% if cp=='/dashboard' %}active{% endif %}" href="{{ url_for('dashboard') }}"><span class="nav-icon">01</span><span>Dashboard</span></a>
      <a class="nav-link {% if cp=='/procesar-cartera' %}active{% endif %}" href="{{ url_for('procesar_cartera') }}"><span class="nav-icon">02</span><span>Procesar Cartera</span></a>
      <a class="nav-link {% if cp=='/wapes-matrix' %}active{% endif %}" href="{{ url_for('wapes_matrix') }}"><span class="nav-icon">03</span><span>WAPES MATRIX</span></a>
      <a class="nav-link {% if cp.startswith('/gestiones') %}active{% endif %}" href="{{ url_for('gestiones_cartera') }}"><span class="nav-icon">04</span><span>Gestiones Auto</span></a>
      <a class="nav-link {% if cp=='/bot-whatsapp' %}active{% endif %}" href="{{ url_for('bot_whatsapp') }}"><span class="nav-icon">05</span><span>Bot WhatsApp</span></a>
      <a class="nav-link {% if cp=='/historial' %}active{% endif %}" href="{{ url_for('historial') }}"><span class="nav-icon">06</span><span>Historial</span></a>
      <a class="nav-link {% if cp=='/supervisor' %}active{% endif %}" href="{{ url_for('supervisor') }}"><span class="nav-icon">07</span><span>Supervisor</span></a>
    </nav>
    <div class="sidebar-footer">
      {% if session.user %}
      <div class="user-chip">
        <div class="user-av">{{ session.user.name[:1] }}</div>
        <div><div class="user-name">{{ session.user.name }}</div><div class="user-role">{{ session.user.role }}</div></div>
      </div>
      <a href="/auth/logout" class="logout-link">Cerrar sesión</a>
      {% endif %}
      <div style="margin-top:8px"><a href="/tutorial" style="color:rgba(200,210,255,0.5);font-size:0.78rem;">Tutorial →</a></div>
    </div>
  </aside>
  <main class="main-panel">
    {% with msgs=get_flashed_messages(with_categories=true) %}{% if msgs %}<div class="flash-stack">{% for c,m in msgs %}<div class="flash flash-{{ c }}">{{ m }}</div>{% endfor %}</div>{% endif %}{% endwith %}
    {% block content %}{% endblock %}
  </main>
</div>
<script src="{{ url_for('script_asset') }}"></script>
</body></html>"""

DASHBOARD_T = """{% extends "base.html" %}{% block title %}Dashboard | TAKOLO{% endblock %}{% block content %}
<section class="page-head">
  <div><h1>Dashboard</h1><p>Resumen de tu operación de cobranza.</p></div>
  <a class="primary-btn inline-btn" href="{{ url_for('procesar_cartera') }}">+ Procesar cartera</a>
</section>
<section class="metric-grid">
  <article class="metric-card"><div class="metric-label">Registros procesados</div><div class="metric-value">{{ s.processed_rows }}</div></article>
  <article class="metric-card warning"><div class="metric-label">Descartados</div><div class="metric-value">{{ s.discarded_rows }}</div></article>
  <article class="metric-card success"><div class="metric-label">Monto total</div><div class="metric-value">{{ s.total_amount | money }}</div></article>
  <article class="metric-card accent"><div class="metric-label">Archivos procesados</div><div class="metric-value">{{ s.files_processed }}</div></article>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>Actividad Reciente</h2></div><a class="ghost-link" href="{{ url_for('historial') }}">Ver historial →</a></div>
  {% if uploads %}
  <div class="table-wrap"><table>
    <thead><tr><th>Archivo</th><th>Gestor</th><th>Activos</th><th>Monto</th><th>Fecha</th><th></th></tr></thead>
    <tbody>
    {% for item in uploads %}
    <tr id="dr-{{ item.id }}">
      <td>{{ item.original_name }}</td><td>{{ item.gestor_selected }}</td><td>{{ item.valid_rows }}</td>
      <td class="money-cell">{{ item.total_amount | money }}</td><td>{{ item.processed_at | date_label }}</td>
      <td><button class="delete-btn" onclick="delCartera('{{ item.id }}','dr-{{ item.id }}')" title="Eliminar">✕</button></td>
    </tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% else %}<div class="empty-state"><h3>Sin archivos procesados aún</h3><p>Sube tu primera cartera para comenzar.</p></div>{% endif %}
</section>
<script>
async function delCartera(id,rowId){
  if(!confirm('¿Eliminar esta cartera y todos sus registros?'))return;
  const row=document.getElementById(rowId);if(row)row.style.opacity='0.4';
  const r=await fetch('/api/cartera/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:id})});
  const d=await r.json();
  if(d.ok&&row)row.remove();else{if(row)row.style.opacity='1';alert('Error: '+d.msg);}
}
</script>{% endblock %}"""

HISTORIAL_T = """{% extends "base.html" %}{% block title %}Historial | TAKOLO{% endblock %}{% block content %}
<section class="page-head"><div><h1>Historial</h1><p>Todas tus cargas procesadas.</p></div></section>
<section class="content-card">
  <div class="section-head"><div><h2>Cargas TAKOLO</h2></div></div>
  {% if files %}
  <div class="table-wrap"><table>
    <thead><tr><th>Archivo</th><th>Gestor</th><th>Total</th><th>Activos</th><th>Monto</th><th>Fecha</th><th></th></tr></thead>
    <tbody>{% for item in files %}
    <tr id="hr-{{ item.id }}">
      <td>{{ item.original_name }}</td><td>{{ item.gestor_selected }}</td>
      <td>{{ item.total_rows }}</td><td>{{ item.valid_rows }}</td>
      <td class="money-cell">{{ item.total_amount | money }}</td>
      <td>{{ item.processed_at | datetime_label }}</td>
      <td><button class="delete-btn" onclick="delCartera('{{ item.id }}','hr-{{ item.id }}')" title="Eliminar">✕</button></td>
    </tr>
    {% endfor %}</tbody>
  </table></div>
  {% else %}<div class="empty-state"><h3>Sin cargas registradas</h3></div>{% endif %}
</section>
<script>
async function delCartera(id,rowId){
  if(!confirm('¿Eliminar esta cartera?'))return;
  const row=document.getElementById(rowId);if(row)row.style.opacity='0.4';
  const r=await fetch('/api/cartera/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:id})});
  const d=await r.json();
  if(d.ok&&row)row.remove();else{if(row)row.style.opacity='1';alert('Error: '+(d.msg||'?'));}
}
</script>{% endblock %}"""

PROCESAR_T = """{% extends "base.html" %}{% block title %}Procesar Cartera | TAKOLO{% endblock %}{% block content %}
<section class="page-head"><div><h1>Procesar Cartera</h1><p>Sube Excel o CSV — TAKOLO detecta columnas y referencias automáticamente.</p></div></section>
<section class="content-card">
  <div class="stepper">
    <div class="step {% if not stage and not cf %}active{% elif stage or cf %}done{% endif %}"><span class="step-index">1</span><div><strong>Subir Archivo</strong><small>Excel, XLS o CSV</small></div></div>
    <div class="step {% if stage %}active{% elif cf %}done{% endif %}"><span class="step-index">2</span><div><strong>Elegir Gestor</strong><small>Filtra y valida</small></div></div>
    <div class="step {% if cf %}active{% endif %}"><span class="step-index">3</span><div><strong>Descargar</strong><small>Master y cierre</small></div></div>
  </div>
</section>
<section class="upload-layout">
  <article class="content-card">
    <div class="section-head"><div><h2>Sube tu cartera</h2><p>Acepta columnas de referencia: <code>REF NOMBRE</code>, <code>REF TEL</code></p></div></div>
    <form class="upload-form" method="post" enctype="multipart/form-data">
      <input type="hidden" name="action" value="upload">
      <label class="upload-zone" for="cartera_file">
        <input id="cartera_file" type="file" name="cartera_file" accept=".xlsx,.xls,.csv">
        <span class="upload-title">Arrastra tu archivo aquí</span>
        <span class="upload-subtitle">o haz clic para seleccionar</span>
        <span class="upload-caption" data-file-label>Formatos: .xlsx, .xls, .csv</span>
      </label>
      <button class="primary-btn" type="submit">Analizar archivo</button>
    </form>
  </article>
  {% if stage %}
  <article class="content-card">
    <div class="section-head"><div><h2>Archivo listo</h2><p>{{ stage.original_name }}</p></div></div>
    <div class="metric-grid compact">
      <article class="metric-card small"><div class="metric-label">Total</div><div class="metric-value">{{ stage.record_count }}</div></article>
      <article class="metric-card small success"><div class="metric-label">Activos</div><div class="metric-value">{{ stage.active_count }}</div></article>
      <article class="metric-card small warning"><div class="metric-label">Descartados</div><div class="metric-value">{{ stage.discarded_count }}</div></article>
      <article class="metric-card small accent"><div class="metric-label">Con referencia</div><div class="metric-value">{{ stage.with_ref }}</div></article>
    </div>
    {% if stage.gestores %}
    <div class="gestores-detected">
      <div class="gestores-label">Gestores detectados ({{ stage.gestores|length }})</div>
      <div class="gestores-chips">{% for g in stage.gestores %}<span class="gestor-chip">{{ g }}</span>{% endfor %}</div>
    </div>
    {% endif %}
    <form class="stack-form" method="post">
      <input type="hidden" name="action" value="finalize">
      <label class="field-label" for="gestor">Gestor a procesar</label>
      <select id="gestor" name="gestor" class="field-control">
        <option value="TODOS">TODOS ({{ stage.active_count }} activos)</option>
        {% for g in stage.gestores %}<option value="{{ g }}">{{ g }}</option>{% endfor %}
      </select>
      <button class="primary-btn" type="submit">Generar descarga</button>
    </form>
    <form method="post" style="margin-top:8px"><input type="hidden" name="action" value="reset"><button class="secondary-btn" type="submit">Limpiar carga</button></form>
  </article>
  {% endif %}
</section>
{% if stage and stage.preview %}
<section class="content-card">
  <div class="section-head"><div><h2>Vista previa</h2><p>Primeros {{ stage.preview|length }} registros activos.</p></div></div>
  <div class="table-wrap"><table>
    <thead><tr><th>Folio</th><th>Cliente</th><th>Teléfono</th><th>Cuota</th><th>Saldo</th><th>Gestor</th><th>Ref. Nombre</th><th>Ref. Tel</th></tr></thead>
    <tbody>{% for row in stage.preview %}
    <tr><td>{{ row.ID }}</td><td>{{ row.CLIENTE }}</td><td>{{ row.WHATSAPP }}</td>
      <td class="money-cell">{{ row.CUOTA | money }}</td><td class="money-cell">{{ row.SALDO | money }}</td>
      <td>{{ row.GESTOR }}</td>
      <td>{{ row.get('REF_NOMBRE','—') }}</td>
      <td>{{ row.get('REF_TEL','—') }}</td>
    </tr>{% endfor %}</tbody>
  </table></div>
</section>
{% endif %}
{% if cf %}
<section class="content-card success-card">
  <div class="section-head">
    <div><h2>✅ Descarga lista</h2><p>{{ cf.original_name }} — gestor {{ cf.gestor_selected }}</p></div>
    <a class="primary-btn inline-btn" href="{{ url_for('download_file', file_id=cf.id) }}">⬇ Descargar Excel</a>
  </div>
</section>
{% endif %}
{% endblock %}"""

WAPES_T = """{% extends "base.html" %}{% block title %}WAPES MATRIX | TAKOLO{% endblock %}{% block content %}
<section class="page-head"><div><h1>WAPES MATRIX</h1><p>Vista financiera por gestor.</p></div></section>
<section class="metric-grid">
  <article class="metric-card"><div class="metric-label">Procesados</div><div class="metric-value">{{ s.processed_rows }}</div></article>
  <article class="metric-card success"><div class="metric-label">Monto total</div><div class="metric-value">{{ s.total_amount | money }}</div></article>
  <article class="metric-card warning"><div class="metric-label">Descartados</div><div class="metric-value">{{ s.discarded_rows }}</div></article>
  <article class="metric-card accent"><div class="metric-label">Archivos</div><div class="metric-value">{{ s.files_processed }}</div></article>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>Matriz por Gestor</h2></div></div>
  {% if matrix %}
  <div class="table-wrap"><table>
    <thead><tr><th>Gestor</th><th>Total</th><th>Listos</th><th>Descartados</th><th>Monto activo</th></tr></thead>
    <tbody>{% for row in matrix %}<tr><td><strong>{{ row.gestor }}</strong></td><td>{{ row.total_registros }}</td><td>{{ row.listos }}</td><td>{{ row.descartados }}</td><td class="money-cell">{{ row.monto_activo | money }}</td></tr>{% endfor %}</tbody>
  </table></div>
  {% else %}<div class="empty-state"><h3>Sin matriz aún</h3><p>Procesa al menos una cartera.</p></div>{% endif %}
</section>{% endblock %}"""

# ---- GESTIONES (includes reference section) ----
GESTIONES_T = """{% extends "base.html" %}{% block title %}Gestiones | TAKOLO{% endblock %}{% block content %}
<section class="ops-hero">
  <div><div class="ops-kicker">Cobranza Automatizada</div><h1>Gestiones Auto</h1></div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;">
    <a class="primary-btn inline-btn" href="{{ url_for('api_export_filtered',file_id=f.file_id,gestor=f.gestor,search=f.search,segment=f.segment) }}">⬇ Excel</a>
    <a class="secondary-btn inline-btn" href="{{ url_for('procesar_cartera') }}">Subir cartera</a>
  </div>
</section>
<div class="ops-tabs">
  <a class="ops-tab active" href="{{ url_for('gestiones_cartera',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment,file_id=f.file_id) }}">Cartera</a>
  <a class="ops-tab" href="{{ url_for('gestiones_mensajes',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment,file_id=f.file_id) }}">Mensajes Auto</a>
</div>
<section class="ops-shell">
  {% if all_files %}
  <div class="file-selector-row">
    <span class="file-selector-label">Cartera:</span>
    <a class="ops-chip {% if not f.file_id %}active{% endif %}" href="{{ url_for('gestiones_cartera',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment,file_id='') }}">Todas</a>
    {% for fi in all_files %}
      <a class="ops-chip {% if f.file_id==fi.id %}active{% endif %}" href="{{ url_for('gestiones_cartera',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment,file_id=fi.id) }}" title="{{ fi.original_name }}">{{ fi.original_name|truncate(20,True) }}</a>
      <button class="file-delete-x" onclick="delCartera('{{ fi.id }}')" title="Eliminar">✕</button>
    {% endfor %}
  </div>
  {% endif %}
  <div class="ops-summary-grid">
    <article class="ops-metric blue"><span>Activos</span><strong>{{ ops.active_clients }}</strong><small>En vista</small></article>
    <article class="ops-metric coral"><span>Saldo Total</span><strong>{{ ops.total_amount | money }}</strong><small>Acumulado</small></article>
    <article class="ops-metric green"><span>Cuota Total</span><strong>{{ ops.total_cuota | money }}</strong><small>Agregada</small></article>
    <article class="ops-metric gold"><span>Con Referencia</span><strong>{{ ops.with_ref }}</strong><small>Registros</small></article>
  </div>
  <div class="ops-controls">
    <form class="ops-search-form" method="get">
      <input type="text" name="search" value="{{ f.search }}" placeholder="Buscar cliente, folio o teléfono">
      <input type="hidden" name="segment" value="{{ f.segment }}"><input type="hidden" name="file_id" value="{{ f.file_id }}">
      <select name="tone">
        <option value="cercano" {% if f.tone=='cercano' %}selected{% endif %}>Cercano</option>
        <option value="formal" {% if f.tone=='formal' %}selected{% endif %}>Formal</option>
        <option value="urgente" {% if f.tone=='urgente' %}selected{% endif %}>Urgente</option>
      </select>
      <button type="submit" class="secondary-btn">Buscar</button>
    </form>
    <div class="ops-segments">
      {% for seg,lbl in [('todas','Todas'),('activos','Activos'),('hoy','Hoy'),('pagos','Pagados')] %}
        <a class="ops-pill {% if f.segment==seg %}active{% endif %}" href="{{ url_for('gestiones_cartera',search=f.search,gestor=f.gestor,tone=f.tone,segment=seg,file_id=f.file_id) }}">{{ lbl }}</a>
      {% endfor %}
      <button class="ops-pill danger-pill" onclick="delPagados()">🗑 Eliminar pagados</button>
    </div>
    <div class="ops-chip-row">
      <a class="ops-chip {% if f.gestor=='TODOS' %}active{% endif %}" href="{{ url_for('gestiones_cartera',search=f.search,tone=f.tone,segment=f.segment,file_id=f.file_id,gestor='TODOS') }}">Todos ({{ ops.active_clients }})</a>
      {% for item in mh %}
        <a class="ops-chip {% if f.gestor==item.gestor %}active{% endif %}" href="{{ url_for('gestiones_cartera',search=f.search,tone=f.tone,segment=f.segment,file_id=f.file_id,gestor=item.gestor) }}">{{ item.gestor }} ({{ item.listos }})</a>
      {% endfor %}
    </div>
  </div>
  <div class="ops-main-grid">
    <section class="ops-column">
      <div class="ops-section-head"><div><h2>Cartera</h2><p>{{ records|length }} registros</p></div></div>
      <div class="ops-list">
        {% for row in records %}
        <a class="ops-client-card {% if sel and sel.record_key==row.record_key %}selected{% endif %} {% if row.contactado %}contactado{% endif %} {% if not row.is_active %}inactivo{% endif %}"
           href="{{ url_for('gestiones_cartera',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment,file_id=f.file_id,selected=row.record_key) }}">
          <div class="ops-avatar">{{ row.initial }}</div>
          <div class="ops-client-body">
            <strong>{{ row.cliente }}</strong>
            <span>ID: {{ row.folio }}</span>
            <span>{{ row.telefono }}</span>
            {% if row.ref_tel %}<span style="color:rgba(168,85,247,0.8);font-size:0.78rem">👥 Ref: {{ row.ref_nombre or '—' }}</span>{% endif %}
          </div>
          <div class="ops-client-money">
            <em>Cuota</em><strong>{{ row.cuota | money }}</strong>
            <small>Saldo {{ row.saldo | money }}</small>
          </div>
          {% if row.contactado %}<span class="tag-contactado">✓</span>{% endif %}
        </a>
        {% else %}
        <div class="ops-empty"><h3>Sin registros</h3><p>Sube una cartera o ajusta los filtros.</p></div>
        {% endfor %}
      </div>
    </section>
    <aside class="ops-column ops-detail-column">
      {% if sel %}
      <section class="ops-detail-card">
        <div class="ops-detail-head">
          <div><div class="ops-detail-label">Detalle</div><h2>{{ sel.cliente }}</h2><p>Crédito {{ sel.folio }}</p></div>
          <span class="status-pill {% if sel.is_active %}ok{% else %}bad{% endif %}">{{ sel.status }}</span>
        </div>
        <div class="ops-amount-panel">
          <div class="ops-amount-big"><span>Cuota</span><strong>{{ sel.cuota | money }}</strong></div>
          <div class="ops-amount-split">
            <div><span>Saldo Total</span><strong>{{ sel.saldo | money }}</strong></div>
            <div><span>Gestor</span><strong>{{ sel.gestor }}</strong></div>
          </div>
        </div>
        <!-- Acciones deudor -->
        <div class="ops-actions" style="grid-template-columns:repeat(2,1fr)">
          <a class="ops-action blue" href="tel:{{ sel.telefono }}">📞 Llamar</a>
          <a class="ops-action green" href="{{ sel.whatsapp_url }}" target="_blank">💬 WhatsApp</a>
        </div>
        <div class="ops-actions" style="grid-template-columns:repeat(3,1fr)">
          <button class="ops-action lime" onclick="marcar('contactado')">✓ Contactado</button>
          <button class="ops-action gold-action" onclick="marcar('pagado')">💰 Pagado</button>
          <button class="ops-action red-action" onclick="eliminar()">🗑 Quitar</button>
        </div>
        <!-- Sección REFERENCIA -->
        {% if sel.ref_tel %}
        <div class="ref-box">
          <div class="ref-box-title">👥 Referencia del deudor</div>
          <div class="ref-row"><span>Nombre</span><strong>{{ sel.ref_nombre or '—' }}</strong></div>
          <div class="ref-row"><span>Teléfono</span><strong>{{ sel.ref_tel }}</strong></div>
          <div class="ops-actions" style="grid-template-columns:repeat(2,1fr);margin-top:10px;margin-bottom:0">
            <a class="ops-action blue" href="tel:{{ sel.ref_tel }}" style="min-height:44px;font-size:0.82rem">📞 Llamar ref.</a>
            <a class="ops-action ref-action" href="{{ sel.ref_whatsapp_url }}" target="_blank" style="min-height:44px">💬 WA Referencia</a>
          </div>
        </div>
        {% endif %}
        <div class="ops-info-list" style="margin-top:12px">
          <div><span>Teléfono</span><strong>{{ sel.telefono }}</strong></div>
          <div><span>Archivo</span><strong>{{ sel.original_name }}</strong></div>
          <div><span>Hoja</span><strong>{{ sel.hoja_origen }}</strong></div>
        </div>
      </section>
      {% else %}
      <div class="ops-empty detail"><h3>Selecciona un cliente</h3><p>Elige un registro de la lista.</p></div>
      {% endif %}
    </aside>
  </div>
</section>
<script>
const RK={{ ('"'~sel.record_key~'"')|safe if sel else 'null' }};
async function ap(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json();}
async function marcar(a){if(!RK)return;const r=await ap('/api/record/mark',{record_key:RK,accion:a});if(r.ok){toast('✅ '+a);setTimeout(()=>location.reload(),900);}else toast('❌ '+r.msg,1);}
async function eliminar(){if(!RK||!confirm('¿Eliminar este registro?'))return;const r=await ap('/api/record/delete',{record_key:RK});if(r.ok){toast('🗑 Eliminado');setTimeout(()=>{const u=new URL(location.href);u.searchParams.delete('selected');location.href=u;},700);}else toast('❌ '+r.msg,1);}
async function delPagados(){if(!confirm('¿Eliminar todos los pagados?'))return;const r=await ap('/api/record/delete-pagados',{file_id:'{{ f.file_id }}'});toast('🗑 '+r.msg);setTimeout(()=>location.reload(),900);}
async function delCartera(id){if(!confirm('¿Eliminar cartera completa?'))return;const r=await ap('/api/cartera/delete',{file_id:id});if(r.ok){toast('✅ Eliminada');setTimeout(()=>location.reload(),700);}else toast('❌ '+r.msg,1);}
function toast(msg,err=0){let t=document.getElementById('tk-toast');if(!t){t=document.createElement('div');t.id='tk-toast';document.body.appendChild(t);}t.textContent=msg;t.className='toast-visible'+(err?' toast-error':'');clearTimeout(t._t);t._t=setTimeout(()=>t.className='',2500);}
</script>{% endblock %}"""

MENSAJES_T = """{% extends "base.html" %}{% block title %}Mensajes Auto | TAKOLO{% endblock %}{% block content %}
<section class="ops-hero"><div><div class="ops-kicker">Cobranza Automatizada</div><h1>Mensajes Automáticos</h1></div></section>
<div class="ops-tabs">
  <a class="ops-tab" href="{{ url_for('gestiones_cartera',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment) }}">Cartera</a>
  <a class="ops-tab active" href="{{ url_for('gestiones_mensajes',search=f.search,gestor=f.gestor,tone=f.tone,segment=f.segment) }}">Mensajes Auto</a>
</div>
<section class="ops-shell">
  <div class="ops-controls">
    <form class="ops-search-form" method="get">
      <input type="text" name="search" value="{{ f.search }}" placeholder="Buscar...">
      <input type="hidden" name="gestor" value="{{ f.gestor }}">
      <input type="hidden" name="segment" value="{{ f.segment }}">
      <select name="tone">
        <option value="cercano" {% if f.tone=='cercano' %}selected{% endif %}>Cercano</option>
        <option value="formal" {% if f.tone=='formal' %}selected{% endif %}>Formal</option>
        <option value="urgente" {% if f.tone=='urgente' %}selected{% endif %}>Urgente</option>
      </select>
      <button type="submit" class="secondary-btn">Aplicar</button>
    </form>
    <div class="ops-chip-row">
      <a class="ops-chip {% if f.gestor=='TODOS' %}active{% endif %}" href="{{ url_for('gestiones_mensajes',search=f.search,tone=f.tone,segment=f.segment,gestor='TODOS') }}">Todos</a>
      {% for item in mh %}<a class="ops-chip {% if f.gestor==item.gestor %}active{% endif %}" href="{{ url_for('gestiones_mensajes',search=f.search,tone=f.tone,segment=f.segment,gestor=item.gestor) }}">{{ item.gestor }}</a>{% endfor %}
    </div>
  </div>
  <div class="msg-grid">
    {% for row in records %}
    <article class="msg-card">
      <div class="msg-card-head">
        <div class="ops-avatar small">{{ row.initial }}</div>
        <div><strong>{{ row.cliente }}</strong><span>{{ row.folio }} · {{ row.gestor }}</span></div>
        <div class="msg-amounts"><span>Cuota <b>{{ row.cuota | money }}</b></span><span>Saldo <b>{{ row.saldo | money }}</b></span></div>
      </div>
      <div class="msg-body">{{ row.msg_deudor }}</div>
      <div class="msg-actions">
        <a class="msg-btn green" href="{{ row.whatsapp_url }}" target="_blank">📱 Deudor</a>
        <button class="msg-btn gray" onclick="copyMsg(this,'{{ row.msg_deudor | e }}')" title="Copiar">📋 Copiar</button>
        {% if row.ref_tel %}
        <a class="msg-btn purple" href="{{ row.ref_whatsapp_url }}" target="_blank" title="Enviar a referencia">👥 Ref.</a>
        {% endif %}
      </div>
      {% if row.ref_tel %}
      <div style="padding:10px 12px;border-radius:12px;background:rgba(124,58,237,0.1);border:1px solid rgba(168,85,247,0.2);font-size:0.82rem;color:rgba(200,180,255,0.85)">
        <strong style="color:#c4b5fd">Referencia:</strong> {{ row.ref_nombre or '?' }} · {{ row.ref_tel }}
      </div>
      {% endif %}
    </article>
    {% else %}
    <div class="ops-empty" style="grid-column:1/-1"><h3>Sin mensajes</h3><p>Sube una cartera o cambia el filtro.</p></div>
    {% endfor %}
  </div>
</section>
<script>
function copyMsg(btn,msg){navigator.clipboard.writeText(msg).then(()=>{const o=btn.textContent;btn.textContent='¡Copiado!';setTimeout(()=>btn.textContent=o,1500);});}
</script>{% endblock %}"""

BOT_T = """{% extends "base.html" %}{% block title %}Bot WhatsApp | TAKOLO{% endblock %}{% block content %}
<section class="page-head">
  <div><h1>Bot WhatsApp</h1><p>Envío automático a deudores <strong>y sus referencias</strong>.</p></div>
  <span class="status-pill {% if bot_ok %}ok{% else %}bad{% endif %}">{% if bot_ok %}✓ Twilio listo{% else %}⚠ Sin configurar{% endif %}</span>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>Credenciales Twilio</h2><p>Sandbox gratuito en <a href="https://twilio.com/try-twilio" target="_blank" style="color:#4c98ff">twilio.com/try-twilio</a></p></div></div>
  <form method="post" action="/bot-whatsapp/config" class="bot-config-form">
    <div class="config-grid">
      <div class="field-group"><label>Account SID</label><input type="text" name="account_sid" placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" value="{{ cfg.account_sid or '' }}"></div>
      <div class="field-group"><label>Auth Token</label><input type="password" name="auth_token" placeholder="Tu auth token secreto" autocomplete="new-password"></div>
      <div class="field-group"><label>Número WhatsApp (from)</label><input type="text" name="from_number" placeholder="whatsapp:+14155238886" value="{{ cfg.from_number or '' }}"></div>
      <div class="field-group"><label>Intervalo entre mensajes (seg)</label><input type="number" name="interval_seconds" min="3" max="120" value="{{ cfg.interval_seconds or 8 }}"></div>
    </div>
    <button type="submit" class="primary-btn">💾 Guardar configuración</button>
  </form>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>Lanzar Campaña</h2><p>Envía mensajes al deudor y a su referencia si la tiene.</p></div></div>
  <form method="post" action="/bot-whatsapp/launch" class="launch-form">
    <div class="config-grid">
      <div class="field-group"><label>Cartera</label>
        <select name="file_id"><option value="">Todas las carteras</option>
          {% for fi in all_files %}<option value="{{ fi.id }}">{{ fi.original_name }} ({{ fi.valid_rows }} activos)</option>{% endfor %}
        </select>
      </div>
      <div class="field-group"><label>Tono del mensaje</label>
        <select name="tone"><option value="cercano">Cercano y amigable</option><option value="formal">Formal</option><option value="urgente">Urgente</option></select>
      </div>
      <div class="field-group"><label>Límite de envíos (0 = sin límite)</label><input type="number" name="limit" min="0" max="500" value="50"></div>
      <div class="field-group"><label>Enviar también a referencias</label>
        <select name="send_refs"><option value="1">Sí — contactar referencia también</option><option value="0">No — solo al deudor</option></select>
      </div>
      <div class="field-group"><label>Solo no contactados hoy</label>
        <select name="only_new"><option value="1">Sí (recomendado)</option><option value="0">No, todos</option></select>
      </div>
    </div>
    <div class="msg-preview-box">
      <div class="msg-preview-label">Vista previa — Mensaje al deudor (tono cercano)</div>
      <div class="msg-preview-text">Hola [CLIENTE], te escribimos por tu crédito [FOLIO].
Tu cuota de hoy es [CUOTA] y tu saldo total va en [SALDO].
Si gustas, te apoyo para dejar tu gestión lista.</div>
    </div>
    <div class="msg-preview-box" style="margin-top:12px;background:#f3f0ff;border-color:rgba(139,92,246,0.3)">
      <div class="msg-preview-label">Vista previa — Mensaje a la referencia</div>
      <div class="msg-preview-text">Hola [REF_NOMBRE], te contactamos de TAKOLO.
Necesitamos comunicarnos urgente con [CLIENTE] respecto a su crédito [FOLIO].
¿Podrías ayudarnos a localizarle? Gracias.</div>
    </div>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px">
      {% if bot_ok %}<button type="submit" name="mode" value="real" class="primary-btn">🚀 Enviar mensajes reales</button>{% endif %}
      <button type="submit" name="mode" value="preview" class="secondary-btn">👁 Vista previa (sin enviar)</button>
    </div>
  </form>
</section>
{% if result %}
<section class="content-card">
  <div class="section-head"><div><h2>Resultado — {% if result.mode=='real' %}Envío real{% else %}Vista previa{% endif %}</h2><p>{{ result.timestamp | datetime_label }}</p></div></div>
  <div class="metric-grid compact">
    <article class="metric-card small success"><div class="metric-label">Deudores {% if result.mode=='real' %}enviados{% else %}procesados{% endif %}</div><div class="metric-value">{{ result.sent_deudores }}</div></article>
    <article class="metric-card small accent"><div class="metric-label">Referencias enviadas</div><div class="metric-value">{{ result.sent_refs }}</div></article>
    <article class="metric-card small warning"><div class="metric-label">Errores</div><div class="metric-value">{{ result.errors }}</div></article>
    <article class="metric-card small"><div class="metric-label">Total procesados</div><div class="metric-value">{{ result.total }}</div></article>
  </div>
  {% if result.rows %}
  <div class="table-wrap" style="margin-top:16px"><table>
    <thead><tr><th>Cliente</th><th>Tel. Deudor</th><th>Estado deudor</th><th>Tel. Referencia</th><th>Estado ref.</th></tr></thead>
    <tbody>{% for row in result.rows %}
    <tr>
      <td>{{ row.cliente }}</td><td>{{ row.tel }}</td>
      <td><span class="campaign-badge {% if row.st_d in ['enviado','preview'] %}badge-ok{% else %}badge-err{% endif %}">{{ row.st_d }}</span></td>
      <td>{{ row.ref_tel or '—' }}</td>
      <td>{% if row.ref_tel %}<span class="campaign-badge {% if row.st_r in ['enviado','preview'] %}badge-ok{% elif row.st_r=='—' %}badge-prev{% else %}badge-err{% endif %}">{{ row.st_r }}</span>{% else %}—{% endif %}</td>
    </tr>{% endfor %}</tbody>
  </table></div>
  {% endif %}
</section>
{% endif %}
<section class="content-card">
  <div class="section-head"><div><h2>Cómo obtener credenciales Twilio</h2></div></div>
  <div class="instructions-grid">
    <div class="instruction-step"><div class="inst-num">1</div><div><strong>Crea cuenta gratuita</strong><p>Ve a <a href="https://twilio.com/try-twilio" target="_blank" style="color:#4f7cff">twilio.com/try-twilio</a>. Sin tarjeta.</p></div></div>
    <div class="instruction-step"><div class="inst-num">2</div><div><strong>Activa sandbox WhatsApp</strong><p>Messaging → Try it out → Send a WhatsApp message. Sigue las instrucciones.</p></div></div>
    <div class="instruction-step"><div class="inst-num">3</div><div><strong>Copia tus credenciales</strong><p>Dashboard Twilio: Account SID y Auth Token. Número: <code>whatsapp:+14155238886</code></p></div></div>
    <div class="instruction-step"><div class="inst-num">4</div><div><strong>Instala la librería</strong><p>En tu terminal: <code>pip install twilio</code></p></div></div>
  </div>
</section>{% endblock %}"""

SUPERVISOR_T = """{% extends "base.html" %}{% block title %}Supervisor | TAKOLO{% endblock %}{% block content %}
<section class="page-head"><div><h1>Panel Supervisor</h1><p>Actividad en tiempo real.</p></div><a class="primary-btn inline-btn" href="{{ url_for('gestiones_cartera') }}">Ver Cartera</a></section>
<div id="sup-loading" style="text-align:center;padding:40px;color:var(--muted)">Cargando datos...</div>
<div id="sup-content" style="display:none">
  <section class="metric-grid" id="sup-totals"></section>
  <section class="content-card">
    <div class="section-head"><div><h2>Resumen por Gestor</h2></div></div>
    <div class="table-wrap"><table><thead><tr><th>Gestor</th><th>Activos</th><th>Contactados hoy</th><th>Sin contactar</th><th>Monto activo</th></tr></thead><tbody id="sup-tbody"></tbody></table></div>
  </section>
</div>
<script>
const fmt=n=>'$'+parseFloat(n||0).toLocaleString('es-MX',{minimumFractionDigits:2});
async function load(){
  try{
    const data=await(await fetch('/api/supervisor')).json();
    document.getElementById('sup-loading').style.display='none';
    document.getElementById('sup-content').style.display='block';
    const t=data.reduce((a,g)=>({activos:a.activos+g.activos,ch:a.ch+g.contactados_hoy,sc:a.sc+g.sin_contactar,ma:a.ma+g.monto_activo}),{activos:0,ch:0,sc:0,ma:0});
    document.getElementById('sup-totals').innerHTML=`
      <article class="metric-card"><div class="metric-label">Activos totales</div><div class="metric-value">${t.activos}</div></article>
      <article class="metric-card success"><div class="metric-label">Contactados hoy</div><div class="metric-value">${t.ch}</div></article>
      <article class="metric-card warning"><div class="metric-label">Sin contactar</div><div class="metric-value">${t.sc}</div></article>
      <article class="metric-card accent"><div class="metric-label">Monto activo</div><div class="metric-value">${fmt(t.ma)}</div></article>`;
    document.getElementById('sup-tbody').innerHTML=data.map(g=>`<tr><td><strong>${g.gestor}</strong></td><td>${g.activos}</td><td style="color:${g.contactados_hoy>0?'var(--success)':'var(--muted)'}">${g.contactados_hoy}</td><td><span class="${g.sin_contactar>0?'status-pill bad':''}">${g.sin_contactar}</span></td><td class="money-cell">${fmt(g.monto_activo)}</td></tr>`).join('');
  }catch(e){document.getElementById('sup-loading').textContent='Error cargando datos.';}
}
load();setInterval(load,30000);
</script>{% endblock %}"""

DEPLOY_T = """{% extends "base.html" %}{% block title %}Deploy | TAKOLO{% endblock %}{% block content %}
<section class="page-head"><div><h1>🚀 Deploy a Internet</h1><p>Instrucciones paso a paso para publicar TAKOLO gratis.</p></div></section>
<section class="content-card">
  <div class="section-head"><div><h2>Opción 1 — Render.com (Recomendado, gratis)</h2></div></div>
  <div class="instructions-grid">
    <div class="instruction-step"><div class="inst-num">1</div><div><strong>Sube tu código a GitHub</strong><p>Crea repo en github.com, sube este archivo como <code>app.py</code> más el archivo <code>requirements.txt</code> de abajo.</p></div></div>
    <div class="instruction-step"><div class="inst-num">2</div><div><strong>Crea cuenta en Render</strong><p>Ve a <a href="https://render.com" target="_blank" style="color:#4f7cff">render.com</a> → New → Web Service → conecta tu repo de GitHub.</p></div></div>
    <div class="instruction-step"><div class="inst-num">3</div><div><strong>Configura el servicio</strong><p><strong>Build Command:</strong> <code>pip install -r requirements.txt</code><br><strong>Start Command:</strong> <code>gunicorn app:app</code><br><strong>Plan:</strong> Free</p></div></div>
    <div class="instruction-step"><div class="inst-num">4</div><div><strong>Variables de entorno</strong><p>En Render → Environment → agrega: <code>TAKOLO_SECRET_KEY</code> = (texto aleatorio largo, ej: 32 caracteres)</p></div></div>
    <div class="instruction-step"><div class="inst-num">5</div><div><strong>¡Listo!</strong><p>Render te da una URL tipo <code>https://tu-app.onrender.com</code>. Configura Twilio desde el panel Bot WhatsApp.</p></div></div>
  </div>
  <div class="deploy-card">
    <h3>📄 requirements.txt (crea este archivo en tu repo)</h3>
    <pre>flask
pandas
openpyxl
twilio
werkzeug
gunicorn</pre>
  </div>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>Opción 2 — Railway.app</h2></div></div>
  <div class="instructions-grid">
    <div class="instruction-step"><div class="inst-num">1</div><div><strong>Crea cuenta en Railway</strong><p>Ve a <a href="https://railway.app" target="_blank" style="color:#4f7cff">railway.app</a> → New Project → Deploy from GitHub.</p></div></div>
    <div class="instruction-step"><div class="inst-num">2</div><div><strong>Agrega Procfile</strong><p>Crea archivo <code>Procfile</code> en tu repo con el contenido: <code>web: gunicorn app:app</code></p></div></div>
    <div class="instruction-step"><div class="inst-num">3</div><div><strong>Variables de entorno</strong><p>Variables → agrega <code>TAKOLO_SECRET_KEY</code> y <code>PORT</code>=8080</p></div></div>
  </div>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>Opción 3 — VPS propio (DigitalOcean, Hostinger, etc.)</h2></div></div>
  <div class="deploy-card">
    <h3>Comandos para servidor Ubuntu</h3>
    <pre>sudo apt update && sudo apt install python3-pip nginx -y
pip3 install flask pandas openpyxl twilio werkzeug gunicorn
# Sube tu app.py al servidor
gunicorn --workers 2 --bind 0.0.0.0:8000 app:app &
# Configura nginx como reverse proxy apuntando a localhost:8000</pre>
  </div>
</section>
<section class="content-card">
  <div class="section-head"><div><h2>⚠️ Seguridad antes de publicar</h2></div></div>
  <div style="display:grid;gap:12px">
    <div class="deploy-card"><h3>✅ Checklist de seguridad</h3>
      <p>1. Cambia la contraseña del admin demo desde /auth/register<br>
      2. Usa HTTPS (Render y Railway lo dan gratis)<br>
      3. Configura <code>TAKOLO_SECRET_KEY</code> en variables de entorno (nunca en el código)<br>
      4. Las credenciales de Twilio van en el panel Bot WhatsApp, no en el código<br>
      5. Considera agregar un dominio propio para mayor profesionalismo</p>
    </div>
  </div>
</section>{% endblock %}"""

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("TAKOLO_SECRET_KEY") or __import__("secrets").token_hex(32)

app.jinja_loader = DictLoader({
    "base.html":              BASE_T,
    "dashboard.html":         DASHBOARD_T,
    "procesar_cartera.html":  PROCESAR_T,
    "wapes_matrix.html":      WAPES_T,
    "gestiones_cartera.html": GESTIONES_T,
    "gestiones_mensajes.html":MENSAJES_T,
    "supervisor.html":        SUPERVISOR_T,
    "historial.html":         HISTORIAL_T,
    "bot_whatsapp.html":      BOT_T,
    "deploy.html":            DEPLOY_T,
})

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def ensure_env():
    for d in (DATA_DIR, UPLOAD_DIR, DOWNLOAD_DIR, STAGING_DIR):
        d.mkdir(parents=True, exist_ok=True)

def _empty(): return {"processed_files":[],"processed_records":[]}

def read_store():
    if not STORE_PATH.exists(): init_store()
    try: p=json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception: p=_empty()
    p.setdefault("processed_files",[]); p.setdefault("processed_records",[])
    return p

def write_store(payload):
    tmp=STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(STORE_PATH)

def init_store():
    if STORE_PATH.exists(): return
    STORE_PATH.write_text(json.dumps(_empty(),ensure_ascii=False,indent=2),encoding="utf-8")

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

def read_users():
    if not USERS_PATH.exists(): return {"users":[]}
    try: return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except: return {"users":[]}

def write_users(d): USERS_PATH.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
def find_user(email): return next((u for u in read_users()["users"] if u["email"]==email),None)

def ensure_demo():
    d=read_users()
    if not any(u["email"]=="admin@takolo.mx" for u in d["users"]):
        d["users"].append({"id":uuid.uuid4().hex,"email":"admin@takolo.mx","name":"Admin TAKOLO","role":"admin","password":_hash("takolo2025"),"created_at":datetime.now().isoformat(),"tutorial_done":False})
        write_users(d)

def require_login(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("user"): return redirect(url_for("login"))
        return f(*a,**k)
    return w

# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------
def detect_col(cols, key):
    rules=COLUMN_RULES[key]
    for col in cols:
        cl=col.strip().lower()
        for r in rules:
            if cl==r: return col
    for col in cols:
        cl=col.strip().lower()
        for r in rules:
            if cl.startswith(r): return col
    for col in cols:
        cl=col.strip().lower()
        for r in rules:
            if r in cl: return col
    return None

def norm_phone(v):
    d=re.sub(r"\D","",str(v or ""))
    return f"521{d[-10:]}" if len(d)>=10 else ""

def parse_amt(v):
    t=str(v or "").strip()
    if not t: return 0.0
    c=re.sub(r"[^\d.\-]","",t.replace(",",""))
    if not c or c in {"-",".","-."}: return 0.0
    try: return round(float(c),2)
    except: return 0.0

def norm_name(v,fb): return str(v or "").strip().upper() or fb

# ---------------------------------------------------------------------------
# Portfolio processing with REFERENCES
# ---------------------------------------------------------------------------
def read_src(path):
    if path.suffix.lower()==".csv":
        try: return {"CSV":pd.read_csv(path,dtype=str,encoding="utf-8-sig")}
        except UnicodeDecodeError: return {"CSV":pd.read_csv(path,dtype=str,encoding="latin-1")}
    try: return pd.read_excel(path,sheet_name=None,dtype=str)
    except ImportError as e: raise ValueError("Instala openpyxl: pip install openpyxl") from e

def normalize_portfolio(path):
    lots=[]
    for sheet,df in read_src(path).items():
        if df.empty: continue
        cols=[str(c).strip() for c in df.columns]; df.columns=cols
        ph=detect_col(cols,"telefono"); am=detect_col(cols,"monto")
        if not ph or not am: continue
        idc=detect_col(cols,"id"); nc=detect_col(cols,"nombre")
        qc=detect_col(cols,"cuota"); sc=detect_col(cols,"status"); gc=detect_col(cols,"gestor")
        # Reference columns
        rnc=detect_col(cols,"ref_nombre"); rtc=detect_col(cols,"ref_tel")

        out=pd.DataFrame()
        out["ID"]      = df[idc].fillna("S/N") if idc else "S/N"
        out["CLIENTE"] = df[nc].apply(lambda v: norm_name(v,"DESCONOCIDO")) if nc else "DESCONOCIDO"
        out["WHATSAPP"]= df[ph].apply(norm_phone)
        out["SALDO"]   = df[am].apply(parse_amt)
        out["CUOTA"]   = df[qc].apply(parse_amt) if qc else df[am].apply(parse_amt)
        out["STATUS"]  = df[sc].apply(lambda v: str(v or "").strip().upper() or "ACTIVO") if sc else "ACTIVO"
        out["GESTOR"]  = df[gc].apply(lambda v: norm_name(v,"SIN ASIGNAR")) if gc else "SIN ASIGNAR"
        out["ORIGEN"]  = sheet
        # References
        out["REF_NOMBRE"] = df[rnc].apply(lambda v: norm_name(v,"")) if rnc else ""
        out["REF_TEL"]    = df[rtc].apply(norm_phone) if rtc else ""
        lots.append(out)

    if not lots:
        return pd.DataFrame(columns=["ID","CLIENTE","WHATSAPP","SALDO","CUOTA","STATUS","GESTOR","ORIGEN","REF_NOMBRE","REF_TEL"])

    m=pd.concat(lots,ignore_index=True)
    m=m.drop_duplicates(subset=["ID","WHATSAPP"],keep="last")
    for col,default in [("ID","S/N"),("CLIENTE","DESCONOCIDO"),("WHATSAPP",""),("STATUS","ACTIVO"),("GESTOR","SIN ASIGNAR"),("ORIGEN","GENERAL"),("REF_NOMBRE",""),("REF_TEL","")]:
        m[col]=m[col].fillna(default).astype(str).str.strip()
    m["STATUS"]=m["STATUS"].str.upper(); m["GESTOR"]=m["GESTOR"].str.upper()
    m["SALDO"]=m["SALDO"].fillna(0).astype(float); m["CUOTA"]=m["CUOTA"].fillna(m["SALDO"]).astype(float)
    return m

def filter_active(df):
    if df.empty: return df.copy()
    pr="|".join(PAID_KW)
    return df[(df["WHATSAPP"]!="")&(df["SALDO"]>1)&(~df["STATUS"].str.contains(pr,na=False))].copy()

# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------
def save_stage(p):
    t=uuid.uuid4().hex
    (STAGING_DIR/f"{t}.json").write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    return t

def load_stage(t):
    if not t: return None
    p=STAGING_DIR/f"{t}.json"
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return None

def rm_stage(t,del_up=False):
    if del_up:
        s=load_stage(t)
        if s and s.get("stored_name"):
            try: (UPLOAD_DIR/s["stored_name"]).unlink(missing_ok=True)
            except: pass
    if t:
        try: (STAGING_DIR/f"{t}.json").unlink(missing_ok=True)
        except: pass

def analyze_file(path, oname):
    m=normalize_portfolio(path)
    if m.empty: raise ValueError("No se detectaron columnas válidas de teléfono y monto.")
    active=filter_active(m)
    gestores=sorted({v for v in m["GESTOR"].tolist() if v and v not in ("SIN ASIGNAR","")})
    if not gestores: gestores=sorted({v for v in m["GESTOR"].tolist() if v})
    with_ref=int((m["REF_TEL"]!="").sum())
    return {
        "original_name":oname,"stored_name":path.name,"uploaded_at":datetime.now().isoformat(),
        "record_count":int(len(m)),"active_count":int(len(active)),"discarded_count":int(len(m)-len(active)),
        "total_amount":float(active["SALDO"].sum()) if not active.empty else 0.0,
        "gestores":gestores,"with_ref":with_ref,
        "records":m.fillna("").to_dict(orient="records"),
        "preview":active.head(10).fillna("").to_dict(orient="records"),
    }

def finalize_stage(stage, gestor_sel):
    sel=(gestor_sel or "TODOS").strip().upper()
    df=pd.DataFrame(stage["records"])
    if df.empty: raise ValueError("Sin registros.")
    if sel!="TODOS": df=df[df["GESTOR"].astype(str).str.upper()==sel]
    if df.empty: raise ValueError("Sin coincidencias para ese gestor.")
    active=filter_active(df)
    fid=uuid.uuid4().hex; now=datetime.now().isoformat()
    dname=f"takolo_{Path(stage['original_name']).stem}_{sel.lower().replace(' ','_')}.xlsx"
    dpath=DOWNLOAD_DIR/f"{fid}.xlsx"
    with pd.ExcelWriter(dpath,engine="openpyxl") as w:
        df.to_excel(w,index=False,sheet_name="MASTER")
        active.to_excel(w,index=False,sheet_name="CIERRE")
    store=read_store()
    store["processed_files"].append({
        "id":fid,"original_name":stage["original_name"],"stored_name":stage["stored_name"],
        "download_name":dname,"gestor_selected":sel,"uploaded_at":stage["uploaded_at"],
        "processed_at":now,"total_rows":int(len(df)),"valid_rows":int(len(active)),
        "discarded_rows":int(len(df)-len(active)),
        "total_amount":float(active["SALDO"].sum()) if not active.empty else 0.0,
    })
    for row in df.to_dict(orient="records"):
        saldo=parse_amt(row.get("SALDO",0)); status=str(row.get("STATUS","")).upper()
        ia=int(bool(row.get("WHATSAPP")) and saldo>1 and not any(w in status for w in PAID_KW))
        store["processed_records"].append({
            "file_id":fid,"folio":str(row.get("ID","S/N")),
            "cliente":str(row.get("CLIENTE","DESCONOCIDO")),
            "telefono":str(row.get("WHATSAPP","")),
            "saldo":saldo,"cuota":parse_amt(row.get("CUOTA",saldo)),
            "status":status or "ACTIVO","gestor":str(row.get("GESTOR","SIN ASIGNAR")),
            "hoja_origen":str(row.get("ORIGEN","GENERAL")),"is_active":ia,
            "ref_nombre":str(row.get("REF_NOMBRE","")),
            "ref_tel":str(row.get("REF_TEL","")),
        })
    write_store(store)
    return fid

# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
def norm_rec(raw):
    def g(k,f=""): return raw.get(k) or raw.get(k.upper()) or f
    saldo=parse_amt(g("saldo",0)); cuota=parse_amt(g("cuota",saldo)) or saldo
    status=str(g("status","ACTIVO")).strip().upper() or "ACTIVO"
    gestor=str(g("gestor","SIN ASIGNAR")).strip().upper() or "SIN ASIGNAR"
    cli=str(g("cliente","DESCONOCIDO")).strip().upper() or "DESCONOCIDO"
    tel=str(g("telefono","")).strip(); folio=str(g("folio","S/N")).strip() or "S/N"
    fid=str(raw.get("file_id","")); ref_nombre=str(g("ref_nombre","")).strip(); ref_tel=str(g("ref_tel","")).strip()
    ia=int(raw.get("is_active",1 if saldo>1 and not any(w in status for w in PAID_KW) else 0))
    return {**raw,"folio":folio,"cliente":cli,"telefono":tel,"saldo":saldo,"cuota":cuota,
            "status":status,"gestor":gestor,"hoja_origen":str(g("hoja_origen","GENERAL")),
            "processed_at":str(raw.get("processed_at","")),"original_name":str(raw.get("original_name","")),
            "file_id":fid,"is_active":ia,"initial":cli[:1] if cli else "C",
            "record_key":f"{fid}::{folio}::{tel}","contactado":bool(raw.get("contactado",False)),
            "ref_nombre":ref_nombre,"ref_tel":ref_tel}

def get_all_recs():
    store=read_store(); fm={f["id"]:f for f in store["processed_files"]}
    return [norm_rec({**r,"processed_at":fm.get(r.get("file_id"),{}).get("processed_at",""),"original_name":fm.get(r.get("file_id"),{}).get("original_name","")}) for r in store["processed_records"]]

def fetch_files(lim=None):
    rows=sorted(read_store()["processed_files"],key=lambda r:r.get("processed_at",""),reverse=True)
    return rows[:lim] if lim else rows

def fetch_file(fid): return next((r for r in read_store()["processed_files"] if r.get("id")==fid),None)

# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@app.template_filter("money")
def money_f(v): return f"${parse_amt(v):,.2f}"

def build_msg_deudor(rec, tone):
    c=rec["cliente"].title(); cu=money_f(rec["cuota"]); sa=money_f(rec["saldo"]); fo=rec["folio"]
    if tone=="formal":
        return f"Buen día {c}. Le contactamos de TAKOLO por su crédito {fo}.\nSu cuota vigente es {cu} y saldo total {sa}.\nPor favor confirme su forma de pago."
    if tone=="urgente":
        return f"Hola {c}. Seguimiento URGENTE al crédito {fo}.\nCuota actual {cu}, saldo total {sa}.\nNecesitamos respuesta hoy para evitar recargo."
    return f"Hola {c}, te escribimos por tu crédito {fo}.\nTu cuota de hoy es {cu} y saldo total {sa}.\nSi gustas, te apoyo para dejar tu gestión lista."

def build_msg_ref(rec):
    ref=rec["ref_nombre"].title() if rec["ref_nombre"] else "estimado/a"
    c=rec["cliente"].title(); fo=rec["folio"]
    return f"Hola {ref}, te contactamos de TAKOLO.\nNecesitamos comunicarnos urgente con {c} respecto a su crédito {fo}.\n¿Podrías ayudarnos a localizarle? Gracias."

def wa_url(phone, msg):
    p=re.sub(r"\D","",str(phone or ""))
    return f"https://wa.me/{p}?text={quote(msg)}" if p else "#"

# ---------------------------------------------------------------------------
# Matrix & snapshot
# ---------------------------------------------------------------------------
def mgr_matrix():
    g={}
    for r in get_all_recs():
        gest=r.get("gestor","SIN ASIGNAR") or "SIN ASIGNAR"
        if gest not in g: g[gest]={"gestor":gest,"total_registros":0,"listos":0,"descartados":0,"monto_activo":0.0}
        g[gest]["total_registros"]+=1
        if r.get("is_active"): g[gest]["listos"]+=1; g[gest]["monto_activo"]+=r.get("saldo",0.0)
        else: g[gest]["descartados"]+=1
    return sorted(g.values(),key=lambda r:(-r["monto_activo"],-r["total_registros"],r["gestor"]))

def snapshot(search,gestor,segment,tone,file_id=""):
    recs=get_all_recs(); today=datetime.now().strftime("%Y-%m-%d")
    if file_id: recs=[r for r in recs if r["file_id"]==file_id]
    if gestor!="TODOS": recs=[r for r in recs if r["gestor"]==gestor]
    if search:
        q=search.strip().lower()
        recs=[r for r in recs if q in r["cliente"].lower() or q in r["folio"].lower() or q in r["telefono"]]
    if segment=="pagos":   recs=[r for r in recs if any(w in r["status"] for w in PAID_KW) or r["saldo"]<=0]
    elif segment=="hoy":   hr=[r for r in recs if str(r.get("processed_at","")).startswith(today)]; recs=hr if hr else [r for r in recs if r["is_active"]]
    elif segment=="activos": recs=[r for r in recs if r["is_active"]]
    recs.sort(key=lambda r:(-r["is_active"],-r["cuota"],-r["saldo"],r["cliente"]))
    for r in recs:
        r["msg_deudor"]      = build_msg_deudor(r,tone)
        r["whatsapp_url"]    = wa_url(r["telefono"], r["msg_deudor"])
        r["ref_whatsapp_url"]= wa_url(r["ref_tel"], build_msg_ref(r)) if r["ref_tel"] else "#"
    sel_key=request.args.get("selected","").strip()
    sel=next((r for r in recs if r["record_key"]==sel_key),None)
    if not sel and recs: sel=recs[0]
    if sel and sel["ref_tel"]:
        sel["ref_whatsapp_url"]=wa_url(sel["ref_tel"],build_msg_ref(sel))
    mx=mgr_matrix()
    if file_id:
        fr=get_all_recs(); fr=[r for r in fr if r["file_id"]==file_id]
        fg={}
        for r in fr:
            ge=r.get("gestor","SIN ASIGNAR")
            if ge not in fg: fg[ge]={"gestor":ge,"listos":0}
            if r.get("is_active"): fg[ge]["listos"]+=1
        mh=list(fg.values())
    else:
        mh=[{**r} for r in mx]
    ar=[r for r in recs if r["is_active"]]
    with_ref=sum(1 for r in ar if r["ref_tel"])
    return {"records":recs,"sel":sel,"manager_matrix":mx,"mh":mh,"all_files":fetch_files(),
            "ops":{"active_clients":len(ar),"total_amount":sum(r["saldo"] for r in ar),"total_cuota":sum(r["cuota"] for r in ar),"with_ref":with_ref}}

def dash_summary():
    files=read_store()["processed_files"]
    return {"files_processed":len(files),"processed_rows":sum(int(f.get("valid_rows",0) or 0) for f in files),
            "discarded_rows":sum(int(f.get("discarded_rows",0) or 0) for f in files),
            "total_amount":sum(parse_amt(f.get("total_amount",0)) for f in files),
            "legacy_total":0,"legacy_success":0,"legacy_failures":0,"legacy_unique_clients":0}

# ---------------------------------------------------------------------------
# Bot Config
# ---------------------------------------------------------------------------
def read_bot_cfg():
    if not BOT_CFG_PATH.exists(): return {}
    try: return json.loads(BOT_CFG_PATH.read_text(encoding="utf-8"))
    except: return {}

def write_bot_cfg(d): BOT_CFG_PATH.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

def send_twilio(phone, msg, cfg):
    """Send WhatsApp via Twilio. Returns (ok, sid_or_error)."""
    try:
        from twilio.rest import Client  # type: ignore
        client=Client(cfg["account_sid"],cfg["auth_token"])
        m=client.messages.create(body=msg,from_=cfg["from_number"],to=f"whatsapp:+{phone}")
        return True, m.sid
    except ImportError:
        return False,"Twilio no instalado. Ejecuta: pip install twilio"
    except Exception as e:
        return False, str(e)[:100]

# ---------------------------------------------------------------------------
# Filters & context
# ---------------------------------------------------------------------------
def _mon(n): return ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"][n-1]

def fmt_dt(v,t=False):
    if not v: return "-"
    for f in ("%Y-%m-%dT%H:%M:%S.%f","%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S"):
        try:
            dt=datetime.strptime(str(v)[:26],f)
            b=f"{dt.day:02d} {_mon(dt.month)} {dt.year}"
            return f"{b} {dt.hour:02d}:{dt.minute:02d}" if t else b
        except: pass
    return str(v)

@app.template_filter("date_label")
def date_f(v): return fmt_dt(v,False)

@app.template_filter("datetime_label")
def datetime_f(v): return fmt_dt(v,True)

@app.context_processor
def ctx(): return {"cp":request.path,"app_name":APP_NAME,"app_version":APP_VERSION,"hoy":datetime.now().strftime("%Y-%m-%d")}

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
@app.route("/assets/styles.css")
def styles_asset(): return Response(CSS,mimetype="text/css")

@app.route("/assets/app.js")
def script_asset(): return Response(JS,mimetype="application/javascript")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.route("/auth/login",methods=["GET","POST"])
def login():
    error=info=None
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
        user=find_user(email)
        if user and user.get("password")==_hash(pw):
            session["user"]={"id":user["id"],"name":user["name"],"role":user["role"],"email":user["email"]}
            if not user.get("tutorial_done"):
                d=read_users()
                for u in d["users"]:
                    if u["id"]==user["id"]: u["tutorial_done"]=True
                write_users(d)
                return redirect(url_for("tutorial"))
            return redirect(url_for("dashboard"))
        error="Credenciales incorrectas."
    return render_template_string(LOGIN_T,error=error,info=info,version=APP_VERSION)

@app.route("/auth/logout")
def logout(): session.pop("user",None); return redirect(url_for("login"))

@app.route("/auth/register",methods=["GET","POST"])
def register():
    error=success=None
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower()
        pw=request.form.get("password",""); role=request.form.get("role","gestor")
        if not name or not email or len(pw)<8: error="Completa todos los campos (mínimo 8 caracteres)."
        elif find_user(email): error="Este correo ya está registrado."
        else:
            d=read_users(); d["users"].append({"id":uuid.uuid4().hex,"email":email,"name":name,"role":role,"password":_hash(pw),"created_at":datetime.now().isoformat(),"tutorial_done":False}); write_users(d)
            success=f"Cuenta creada para {name}."
    return render_template_string(REGISTER_T,error=error,success=success)

@app.route("/auth/google")
def google_login():
    flash("Login con Google: agrega flask-dance y configura GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET.","info")
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# Tutorial & Deploy
# ---------------------------------------------------------------------------
@app.route("/tutorial")
def tutorial(): return render_template_string(TUTORIAL_T)

@app.route("/deploy")
@require_login
def deploy(): return render_template_string(DEPLOY_T,**ctx())

# ---------------------------------------------------------------------------
# Main routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if not session.get("user"): return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@require_login
def dashboard():
    return render_template("dashboard.html", s=dash_summary(), uploads=fetch_files(8))

@app.route("/procesar-cartera",methods=["GET","POST"])
@require_login
def procesar_cartera():
    cur=session.get("stage_token")
    if request.method=="POST":
        action=request.form.get("action","")
        if action=="reset":
            rm_stage(cur,del_up=True); session.pop("stage_token",None)
            flash("Carga limpiada.","info"); return redirect(url_for("procesar_cartera"))
        if action=="upload":
            up=request.files.get("cartera_file")
            if not up or not up.filename: flash("Selecciona un archivo.","error"); return redirect(url_for("procesar_cartera"))
            oname=secure_filename(up.filename); ext=Path(oname).suffix.lower()
            if ext not in ALLOWED_EXT: flash("Formato no soportado.","error"); return redirect(url_for("procesar_cartera"))
            rm_stage(cur,del_up=True)
            uname=f"{uuid.uuid4().hex}{ext}"; dest=UPLOAD_DIR/uname; up.save(dest)
            try: stage=analyze_file(dest,oname); tok=save_stage(stage)
            except Exception as e: dest.unlink(missing_ok=True); flash(str(e),"error"); return redirect(url_for("procesar_cartera"))
            session["stage_token"]=tok; session.pop("completed_file_id",None)
            flash(f"Archivo cargado — {stage['record_count']} registros, {stage['with_ref']} con referencia.","success")
            return redirect(url_for("procesar_cartera"))
        if action=="finalize":
            stage=load_stage(cur)
            if not stage: flash("Primero sube un archivo.","error"); return redirect(url_for("procesar_cartera"))
            try: fid=finalize_stage(stage,request.form.get("gestor","TODOS"))
            except ValueError as e: flash(str(e),"error"); return redirect(url_for("procesar_cartera"))
            session.pop("stage_token",None); rm_stage(cur)
            flash("✅ Cartera procesada.","success")
            return redirect(url_for("gestiones_cartera",file_id=fid,segment="activos"))
    stage=load_stage(session.get("stage_token"))
    fid=request.args.get("file_id") or session.get("completed_file_id")
    cf=fetch_file(fid)
    return render_template("procesar_cartera.html",stage=stage,cf=cf)

@app.route("/wapes-matrix")
@require_login
def wapes_matrix(): return render_template("wapes_matrix.html",matrix=mgr_matrix(),s=dash_summary())

def _filters():
    tone=request.args.get("tone","cercano").strip().lower()
    seg=request.args.get("segment","todas").strip().lower()
    return {"search":request.args.get("search","").strip(),
            "gestor":request.args.get("gestor","TODOS").strip().upper() or "TODOS",
            "tone":tone if tone in {"cercano","formal","urgente"} else "cercano",
            "segment":seg if seg in {"hoy","pagos","todas","activos"} else "todas",
            "file_id":request.args.get("file_id","").strip()}

@app.route("/gestiones-cartera")
@require_login
def gestiones_cartera():
    f=_filters(); snap=snapshot(**f)
    return render_template("gestiones_cartera.html",f=f,**snap)

@app.route("/gestiones-mensajes")
@require_login
def gestiones_mensajes():
    f=_filters(); snap=snapshot(**f)
    return render_template("gestiones_mensajes.html",f=f,**snap)

@app.route("/historial")
@require_login
def historial(): return render_template("historial.html",files=fetch_files(50))

@app.route("/supervisor")
@require_login
def supervisor(): return render_template("supervisor.html")

@app.route("/download/<file_id>")
@require_login
def download_file(file_id):
    p=fetch_file(file_id)
    if not p: flash("Archivo no encontrado.","error"); return redirect(url_for("procesar_cartera"))
    path=DOWNLOAD_DIR/f"{file_id}.xlsx"
    if not path.exists(): flash("Descarga no disponible.","error"); return redirect(url_for("procesar_cartera"))
    return send_file(path,as_attachment=True,download_name=p["download_name"])

# ---------------------------------------------------------------------------
# Bot WhatsApp — FUNCIONAL con envío a deudor Y referencia
# ---------------------------------------------------------------------------
@app.route("/bot-whatsapp")
@require_login
def bot_whatsapp():
    cfg=read_bot_cfg()
    bot_ok=bool(cfg.get("account_sid") and cfg.get("auth_token") and cfg.get("from_number"))
    result=session.pop("campaign_result",None)
    return render_template("bot_whatsapp.html",cfg=cfg,bot_ok=bot_ok,all_files=fetch_files(),result=result)

@app.route("/bot-whatsapp/config",methods=["POST"])
@require_login
def bot_config():
    cfg=read_bot_cfg()
    new_token=request.form.get("auth_token","").strip()
    cfg["account_sid"]      =request.form.get("account_sid","").strip()
    cfg["from_number"]      =request.form.get("from_number","").strip()
    cfg["interval_seconds"] =int(request.form.get("interval_seconds",8))
    if new_token and new_token!="●●●●●●●●":
        cfg["auth_token"]=new_token   # solo actualiza si es nuevo valor real
    write_bot_cfg(cfg)
    flash("✅ Configuración guardada.","success")
    return redirect(url_for("bot_whatsapp"))

@app.route("/bot-whatsapp/launch",methods=["POST"])
@require_login
def bot_launch():
    cfg        = read_bot_cfg()
    file_id    = request.form.get("file_id","")
    tone       = request.form.get("tone","cercano")
    limit      = int(request.form.get("limit",50))
    send_refs  = request.form.get("send_refs","1")=="1"
    only_new   = request.form.get("only_new","1")=="1"
    mode       = request.form.get("mode","preview")  # "real" | "preview"
    interval   = cfg.get("interval_seconds",8) if mode=="real" else 0

    recs=get_all_recs()
    if file_id: recs=[r for r in recs if r["file_id"]==file_id]
    recs=[r for r in recs if r["is_active"] and r.get("telefono")]
    if only_new:
        today=datetime.now().strftime("%Y-%m-%d")
        recs=[r for r in recs if not str(r.get("contactado_at","")).startswith(today)]
    if limit>0: recs=recs[:limit]

    sent_d=sent_r=errors=0; rows=[]

    for r in recs:
        msg_d  = build_msg_deudor(r,tone)
        phone_d= re.sub(r"\D","",r.get("telefono",""))
        st_d=st_r="—"

        # ---- Envío al DEUDOR ----
        if phone_d:
            if mode=="real":
                ok,res=send_twilio(phone_d,msg_d,cfg)
                st_d="enviado" if ok else f"err:{res[:30]}"
                if ok: sent_d+=1
                else: errors+=1
                if interval: time.sleep(interval)
            else:
                st_d="preview"; sent_d+=1
        else:
            st_d="sin tel"

        # ---- Envío a la REFERENCIA (si tiene y está activado) ----
        if send_refs and r.get("ref_tel"):
            msg_r   = build_msg_ref(r)
            phone_r = re.sub(r"\D","",r["ref_tel"])
            if phone_r:
                if mode=="real":
                    ok_r,res_r=send_twilio(phone_r,msg_r,cfg)
                    st_r="enviado" if ok_r else f"err:{res_r[:30]}"
                    if ok_r: sent_r+=1
                    else: errors+=1
                    if interval: time.sleep(interval)
                else:
                    st_r="preview"; sent_r+=1

        rows.append({"cliente":r["cliente"],"tel":r["telefono"],"st_d":st_d,"ref_tel":r.get("ref_tel",""),"st_r":st_r})

    session["campaign_result"]={
        "sent_deudores":sent_d,"sent_refs":sent_r,"errors":errors,
        "total":len(recs),"timestamp":datetime.now().isoformat(),
        "rows":rows[:30],"mode":mode,
    }
    flash(f"Campaña {'enviada' if mode=='real' else 'previsualizada'}: {sent_d} deudores, {sent_r} referencias.","success")
    return redirect(url_for("bot_whatsapp"))

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.route("/api/health")
def health(): return jsonify({"status":"ok","version":APP_VERSION})

@app.route("/api/cartera/delete",methods=["POST"])
def api_del_cartera():
    data=request.get_json(silent=True) or {}; fid=data.get("file_id","")
    if not fid: return jsonify({"ok":False,"msg":"file_id requerido"}),400
    store=read_store(); bf=len(store["processed_files"]); br=len(store["processed_records"])
    store["processed_files"]  =[f for f in store["processed_files"]   if f.get("id")!=fid]
    store["processed_records"]=[r for r in store["processed_records"] if r.get("file_id")!=fid]
    for p in (DOWNLOAD_DIR/f"{fid}.xlsx",UPLOAD_DIR/f"{fid}.xlsx"):
        try: p.unlink(missing_ok=True)
        except: pass
    write_store(store)
    return jsonify({"ok":bf>len(store["processed_files"]),"msg":f"Eliminada: {br-len(store['processed_records'])} registros borrados"})

def _find_upd(rk, upd_fn):
    store=read_store(); fm={f["id"]:f for f in store["processed_files"]}
    for i,raw in enumerate(store["processed_records"]):
        info=fm.get(raw.get("file_id"),{})
        rec=norm_rec({**raw,"processed_at":info.get("processed_at",""),"original_name":info.get("original_name","")})
        if rec["record_key"]==rk:
            upd_fn(store["processed_records"][i]); write_store(store); return True,"ok"
    return False,"Registro no encontrado"

@app.route("/api/record/mark",methods=["POST"])
def api_mark():
    d=request.get_json(silent=True) or {}; rk=d.get("record_key",""); accion=d.get("accion","")
    def up(r):
        now=datetime.now().isoformat()
        if accion=="contactado": r["contactado"]=True; r["contactado_at"]=now
        elif accion=="pagado": r["status"]="PAGADO"; r["is_active"]=0; r["pagado_at"]=now
    ok,msg=_find_upd(rk,up)
    return jsonify({"ok":ok,"msg":msg})

@app.route("/api/record/delete",methods=["POST"])
def api_del_rec():
    d=request.get_json(silent=True) or {}; rk=d.get("record_key","")
    store=read_store(); fm={f["id"]:f for f in store["processed_files"]}; bef=len(store["processed_records"])
    store["processed_records"]=[r for r in store["processed_records"] if norm_rec({**r,**fm.get(r.get("file_id"),{})}).get("record_key")!=rk]
    write_store(store)
    return jsonify({"ok":bef>len(store["processed_records"]),"msg":"ok"})

@app.route("/api/record/delete-pagados",methods=["POST"])
def api_del_pagados():
    d=request.get_json(silent=True) or {}; fid=d.get("file_id","")
    store=read_store(); bef=len(store["processed_records"])
    def pag(r): s=str(r.get("status","")).upper(); return any(w in s for w in PAID_KW) or parse_amt(r.get("saldo",0))<=0
    store["processed_records"]=[r for r in store["processed_records"] if not(pag(r) and(not fid or r.get("file_id")==fid))]
    write_store(store)
    return jsonify({"ok":True,"msg":f"{bef-len(store['processed_records'])} pagado(s) eliminado(s)"})

@app.route("/api/supervisor")
def api_supervisor():
    recs=get_all_recs(); today=datetime.now().strftime("%Y-%m-%d"); g={}
    for r in recs:
        ge=r.get("gestor","SIN ASIGNAR")
        if ge not in g: g[ge]={"gestor":ge,"activos":0,"contactados_hoy":0,"sin_contactar":0,"con_promesa":0,"monto_activo":0.0}
        if r.get("is_active"): g[ge]["activos"]+=1; g[ge]["monto_activo"]+=r.get("saldo",0)
        if str(r.get("contactado_at","")).startswith(today): g[ge]["contactados_hoy"]+=1
        if not r.get("contactado"): g[ge]["sin_contactar"]+=1
    return jsonify(sorted(g.values(),key=lambda x:-x["monto_activo"]))

@app.route("/api/export-filtered")
@require_login
def api_export_filtered():
    fid=request.args.get("file_id",""); gest=request.args.get("gestor","TODOS").upper()
    srch=request.args.get("search","").strip().lower(); seg=request.args.get("segment","todas")
    recs=get_all_recs()
    if fid: recs=[r for r in recs if r["file_id"]==fid]
    if gest!="TODOS": recs=[r for r in recs if r["gestor"]==gest]
    if srch: recs=[r for r in recs if srch in r["cliente"].lower() or srch in r["folio"].lower() or srch in r["telefono"]]
    if seg=="activos": recs=[r for r in recs if r["is_active"]]
    if not recs: flash("Sin registros para exportar.","error"); return redirect(url_for("gestiones_cartera"))
    df=pd.DataFrame([{"Folio":r["folio"],"Cliente":r["cliente"],"Teléfono":r["telefono"],"Cuota":r["cuota"],"Saldo":r["saldo"],"Status":r["status"],"Gestor":r["gestor"],"Ref Nombre":r["ref_nombre"],"Ref Tel":r["ref_tel"]} for r in recs])
    eid=uuid.uuid4().hex; ep=DOWNLOAD_DIR/f"export_{eid}.xlsx"
    with pd.ExcelWriter(ep,engine="openpyxl") as w: df.to_excel(w,index=False,sheet_name="Cartera")
    return send_file(ep,as_attachment=True,download_name=f"takolo_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
ensure_env()
init_store()
ensure_demo()

if __name__=="__main__":
    import sys
    port=int(sys.argv[1]) if len(sys.argv)>1 else 5100
    logger.info("TAKOLO v%s → http://127.0.0.1:%d", APP_VERSION, port)
    logger.info("Demo: admin@takolo.mx / takolo2025")
    app.run(host="0.0.0.0",port=port,debug=False)

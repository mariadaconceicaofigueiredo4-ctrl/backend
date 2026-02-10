import time
import json
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
import sqlite3

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
#  BANCO DE DADOS SQLITE
# =========================
DB_FILE = os.path.join(os.path.dirname(__file__), "historico_completo.db")

def init_database():
    """Inicializa o banco de dados com tabela de histórico"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER,
            cor TEXT,
            hora TEXT,
            mensagem TEXT,
            timestamp_recebimento REAL,
            data_hora_real TEXT,
            resultado TEXT
        )
    """)
    conn.commit()
    conn.close()

def salvar_resultado_db(numero, cor, hora, mensagem, timestamp, resultado):
    """Salva um resultado no banco de dados"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    data_hora = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO historico_resultados 
        (numero, cor, hora, mensagem, timestamp_recebimento, data_hora_real, resultado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (numero, cor, hora, mensagem, timestamp, data_hora, resultado))
    conn.commit()
    conn.close()

def obter_historico_filtrado(data_inicio=None, data_fim=None, hora_inicio=None, hora_fim=None, tipo_resultado=None):
    """
    Obtém histórico filtrado por período e/ou horário do dia
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    query = "SELECT * FROM historico_resultados WHERE 1=1"
    params = []

    if data_inicio:
        query += " AND DATE(data_hora_real) >= ?"
        params.append(data_inicio)

    if data_fim:
        query += " AND DATE(data_hora_real) <= ?"
        params.append(data_fim)

    if hora_inicio and hora_fim:
        query += " AND TIME(data_hora_real) BETWEEN ? AND ?"
        params.append(hora_inicio + ":00")
        params.append(hora_fim + ":59")

    if tipo_resultado:
        if tipo_resultado.lower() == 'win':
            query += " AND resultado = 'WIN'"
        elif tipo_resultado.lower() == 'loss':
            query += " AND resultado = 'LOSS'"

    query += " ORDER BY timestamp_recebimento DESC"

    cursor.execute(query, params)
    resultados = cursor.fetchall()
    conn.close()

    colunas = ['id', 'numero', 'cor', 'hora', 'mensagem', 'timestamp_recebimento', 'data_hora_real', 'resultado']
    return [dict(zip(colunas, row)) for row in resultados]

def obter_estatisticas_por_horario(dias=30):
    """
    Retorna estatísticas de Win/Loss agrupadas por horário do dia nos últimos N dias
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    data_limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")

    query = """
        SELECT 
            SUBSTR(TIME(data_hora_real), 1, 2) as hora,
            SUM(CASE WHEN resultado = 'WIN' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN resultado = 'LOSS' THEN 1 ELSE 0 END) as losses,
            COUNT(*) as total
        FROM historico_resultados
        WHERE DATE(data_hora_real) >= ?
        AND resultado IN ('WIN', 'LOSS')
        GROUP BY hora
        ORDER BY hora
    """

    cursor.execute(query, (data_limite,))
    resultados = cursor.fetchall()
    conn.close()

    estatisticas = []
    for row in resultados:
        hora_int = int(row[0])
        estatisticas.append({
            'horario': f"{hora_int:02d}:00",
            'wins': row[1],
            'losses': row[2],
            'total': row[3],
            'taxa_acerto': round((row[1] / row[3] * 100) if row[3] > 0 else 0, 2)
        })

    return estatisticas

def obter_melhores_horarios(dias=30, min_jogadas=5):
    """
    Retorna os horários com melhor performance (sem loss ou menor taxa de loss)
    """
    estatisticas = obter_estatisticas_por_horario(dias)

    horarios_validos = [e for e in estatisticas if e['total'] >= min_jogadas]

    horarios_ordenados = sorted(
        horarios_validos,
        key=lambda x: (x['losses'], -x['taxa_acerto'])
    )

    return horarios_ordenados

init_database()

# =========================
#  ESTADO GLOBAL DO SISTEMA
# =========================
estado_atual = {
    "id": 0,
    "numero": 0,
    "cor": "white",
    "hora": "--:--",
    "mensagem": None,
    "historico": [],
    "placar": {
        "wins": 0,
        "losses": 0,
        "hora_registro": datetime.now().hour
    }
}

# =========================
#  ESTADO GLOBAL DOS HORÁRIOS (CHAVE MESTRA)
# =========================
horarios_state = {
    "ativo": False,
    "horarios": []
}

STATE_FILE = os.path.join(os.path.dirname(__file__), "horarios_state.json")
HORARIO_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

def _linha_eh_horario_valido(linha: str) -> bool:
    return bool(HORARIO_RE.match((linha or "").strip()))

def _normalizar_lista_horarios(horarios: List[str]) -> List[str]:
    vistos = set()
    out = []
    for h in horarios or []:
        h = (h or "").strip()
        if not _linha_eh_horario_valido(h):
            continue
        if h not in vistos:
            vistos.add(h)
            out.append(h)
    return sorted(out)

def _save_horarios_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(horarios_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _load_horarios_state():
    global horarios_state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            ativo = bool(data.get("ativo", False))
            horarios = _normalizar_lista_horarios(data.get("horarios", []) or [])

            horarios_state["horarios"] = horarios
            horarios_state["ativo"] = bool(ativo and len(horarios) > 0)
    except Exception:
        horarios_state["ativo"] = False
        horarios_state["horarios"] = []

@app.on_event("startup")
def on_startup():
    _load_horarios_state()
    init_database()

# =========================
#  MODELS
# =========================
class PedraPayload(BaseModel):
    numero: int
    cor: str
    # ✅ chave usada pelo frontend / API atual
    hora: Optional[str] = None
    # ✅ compat: caso o scraper mande "horario" (seu código novo antigo)
    horario: Optional[str] = None
    mensagem: Optional[str] = None

class HorariosConfigPayload(BaseModel):
    ativo: bool = False
    horarios: List[str] = []

class FiltroHistoricoPayload(BaseModel):
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fim: Optional[str] = None
    tipo_resultado: Optional[str] = None

# =========================
#  HELPERS (HORA)
# =========================
def _normalizar_hora_payload(hora: Optional[str], horario: Optional[str]) -> str:
    """
    Garante uma hora válida HH:MM:
    - tenta data.hora
    - tenta data.horario (compat)
    - se vier inválido, usa hora atual do servidor
    """
    def ok(v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        if not v:
            return None
        if v in ("--:--", "??:??"):
            return None
        if _linha_eh_horario_valido(v):
            return v
        return None

    h = ok(hora) or ok(horario)
    if h:
        return h
    return datetime.now().strftime("%H:%M")

# =========================
#  ROTAS
# =========================
@app.get("/")
def read_root():
    return {"message": "API Blaze Hunters Rodando 🚀"}

@app.get("/events/status")
async def get_status():
    return estado_atual

@app.post("/update_status")
async def update_status(data: PedraPayload):
    global estado_atual

    novo_id = time.time()

    hora_agora = datetime.now().hour
    if hora_agora != estado_atual["placar"]["hora_registro"]:
        estado_atual["placar"]["wins"] = 0
        estado_atual["placar"]["losses"] = 0
        estado_atual["placar"]["hora_registro"] = hora_agora

    # ✅ normaliza hora (pega data.hora ou data.horario)
    hora_ok = _normalizar_hora_payload(data.hora, data.horario)

    resultado = None
    if data.mensagem:
        msg = data.mensagem.upper()
        if "WIN" in msg or "GREEN" in msg:
            estado_atual["placar"]["wins"] += 1
            resultado = "WIN"
        elif "LOSS" in msg:
            estado_atual["placar"]["losses"] += 1
            resultado = "LOSS"

    estado_atual["id"] = novo_id
    estado_atual["numero"] = data.numero
    estado_atual["cor"] = data.cor
    estado_atual["hora"] = hora_ok
    estado_atual["mensagem"] = data.mensagem if data.mensagem else None

    nova_entrada = {
        "numero": data.numero,
        "cor": data.cor,
        "hora": hora_ok,
        "mensagem": data.mensagem,
        "timestamp_recebimento": novo_id
    }

    estado_atual["historico"].insert(0, nova_entrada)
    estado_atual["historico"] = estado_atual["historico"][:120]

    if resultado:
        salvar_resultado_db(
            data.numero,
            data.cor,
            hora_ok,
            data.mensagem,
            novo_id,
            resultado
        )

    return {"status": "recebido", "id_gerado": novo_id, "hora_normalizada": hora_ok}

@app.get("/results/historico")
def get_historico():
    return estado_atual["historico"]

# =========================
#  HISTÓRICO AVANÇADO
# =========================
@app.post("/historico/filtrado")
def get_historico_filtrado_route(filtro: FiltroHistoricoPayload):
    resultados = obter_historico_filtrado(
        data_inicio=filtro.data_inicio,
        data_fim=filtro.data_fim,
        hora_inicio=filtro.hora_inicio,
        hora_fim=filtro.hora_fim,
        tipo_resultado=filtro.tipo_resultado
    )

    total = len(resultados)
    wins = sum(1 for r in resultados if r['resultado'] == 'WIN')
    losses = sum(1 for r in resultados if r['resultado'] == 'LOSS')

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "taxa_acerto": round((wins / total * 100) if total > 0 else 0, 2),
        "resultados": resultados
    }

@app.get("/estatisticas/por-horario")
def get_estatisticas_por_horario_route(dias: int = Query(default=30, ge=1, le=365)):
    estatisticas = obter_estatisticas_por_horario(dias)

    total_wins = sum(e['wins'] for e in estatisticas)
    total_losses = sum(e['losses'] for e in estatisticas)
    total_geral = sum(e['total'] for e in estatisticas)

    return {
        "periodo_dias": dias,
        "total_jogadas": total_geral,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "taxa_acerto_geral": round((total_wins / total_geral * 100) if total_geral > 0 else 0, 2),
        "estatisticas_por_horario": estatisticas
    }

@app.get("/analise/melhores-horarios")
def get_melhores_horarios_route(
    dias: int = Query(default=30, ge=1, le=365),
    min_jogadas: int = Query(default=5, ge=1)
):
    horarios = obter_melhores_horarios(dias, min_jogadas)
    horarios_sem_loss = [h for h in horarios if h['losses'] == 0]

    return {
        "periodo_dias": dias,
        "min_jogadas": min_jogadas,
        "total_horarios_analisados": len(horarios),
        "horarios_sem_loss": horarios_sem_loss,
        "top_10_melhores": horarios[:10],
        "todos_horarios": horarios
    }

@app.get("/relatorio/30-dias")
def get_relatorio_30_dias():
    estatisticas = obter_estatisticas_por_horario(30)
    melhores = obter_melhores_horarios(30, min_jogadas=5)

    horarios_sem_loss = [h for h in melhores if h['losses'] == 0]
    horarios_menor_loss = sorted(melhores, key=lambda x: (x['losses'] / x['total'], x['losses']))[:10]

    total_wins = sum(e['wins'] for e in estatisticas)
    total_losses = sum(e['losses'] for e in estatisticas)
    total_geral = sum(e['total'] for e in estatisticas)

    return {
        "periodo": "Últimos 30 dias",
        "resumo": {
            "total_jogadas": total_geral,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "taxa_acerto_geral": round((total_wins / total_geral * 100) if total_geral > 0 else 0, 2)
        },
        "horarios_sem_loss": horarios_sem_loss,
        "top_10_menor_loss": horarios_menor_loss,
        "estatisticas_completas": estatisticas
    }

# =========================
#  HORÁRIOS (CHAVE MESTRA)
# =========================
@app.get("/horarios/permitidos")
def get_horarios_permitidos():
    return {
        "ativo": bool(horarios_state["ativo"]),
        "horarios": horarios_state["horarios"],
        "total": len(horarios_state["horarios"]),
    }

@app.post("/horarios/configurar")
def configurar_horarios(payload: HorariosConfigPayload):
    horarios_norm = _normalizar_lista_horarios(payload.horarios or [])

    horarios_state["horarios"] = horarios_norm
    horarios_state["ativo"] = bool(payload.ativo and len(horarios_norm) > 0)

    _save_horarios_state()

    return {
        "status": "ok",
        "ativo": horarios_state["ativo"],
        "horarios": horarios_state["horarios"],
        "total": len(horarios_state["horarios"]),
    }

@app.post("/horarios/upload")
async def upload_horarios(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .txt")

    content = await file.read()
    try:
        texto = content.decode("utf-8")
    except UnicodeDecodeError:
        texto = content.decode("latin-1")

    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    horarios_validos = [ln for ln in linhas if _linha_eh_horario_valido(ln)]

    if not horarios_validos:
        raise HTTPException(status_code=400, detail="Nenhum horário válido encontrado. Use HH:MM por linha.")

    horarios_norm = _normalizar_lista_horarios(horarios_validos)

    horarios_state["horarios"] = horarios_norm
    horarios_state["ativo"] = True

    _save_horarios_state()

    return {
        "status": "ok",
        "ativo": horarios_state["ativo"],
        "horarios": horarios_state["horarios"],
        "total": len(horarios_state["horarios"]),
    }

@app.post("/horarios/limpar")
def limpar_horarios():
    horarios_state["ativo"] = False
    horarios_state["horarios"] = []
    _save_horarios_state()
    return {"status": "ok", "ativo": False, "horarios": [], "total": 0}

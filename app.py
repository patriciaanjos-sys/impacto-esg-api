import os, uuid, httpx
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROCESS_HOOK_TOKEN = os.getenv("PROCESS_HOOK_TOKEN","")
FILES_ROOT = Path("./files")
FILES_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="IMPACTO ESG+IA (MVP simples)")
app.mount("/files", StaticFiles(directory=FILES_ROOT.as_posix()), name="files")

def extract_text_simple(pdf_path: str) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(pdf_path)
        return "\n\n".join((p.extract_text() or "") for p in r.pages[:200])
    except Exception:
        return "Não foi possível extrair o texto deste PDF no modo simples."

def gpt5(system: str, user: str, model="gpt-5-thinking", temperature=0.2, timeout=180):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada no ambiente do Render.")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": model,
        "messages": [
            {"role":"system","content":system},
            {"role":"user","content":user}
        ],
        "temperature": temperature
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

SYSTEM = (
  "Você é um tradutor executivo de relatórios ESG para C-level. "
  "Siga LGPD (evite dados pessoais). Traduza achados em linguagem de negócio. "
  "Entregue ROI, SROI, VAR e VBI com explicações curtas. "
  "Apoie-se em IFRS S1/S2, GRI e TCFD quando fizer sentido."
)

@app.post("/tally-webhook")
async def tally_webhook(req: Request):
    auth = req.headers.get("authorization","")
    if not auth.endswith(PROCESS_HOOK_TOKEN):
        raise HTTPException(401, "Unauthorized")

    data = await req.json()

    name       = data.get("name","")
    company    = data.get("company","")
    email      = data.get("email","")
    report_url = data.get("report_url")
    focus      = data.get("focus","Estratégia")
    horizon    = data.get("horizon","6 meses")
    language   = data.get("language","pt")

    if not report_url:
        raise HTTPException(400, "report_url ausente (envie o PDF ou link do relatório no Tally).")

    job_id = str(uuid.uuid4())
    job_dir = FILES_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = job_dir / "report.pdf"
    with httpx.stream("GET", report_url, timeout=180) as r:
        r.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

    text = extract_text_simple(pdf_path.as_posix())

    extraction_prompt = (
        "Extraia do texto os KPIs E/S/G, riscos e oportunidades, metas e status. "
        "Devolva um JSON enxuto com: kpis (lista), riscos_top3, oportunidades_top3.\n\n"
        f"Texto do relatório:\n{text[:60000]}"
    )
    kpis_json = gpt5(SYSTEM, extraction_prompt)

    brief_prompt = (
        f"Gere um brief de 1 página em HTML SEM CSS inline. Empresa: {company}. "
        "Traga 3 mensagens-chave, 3-5 KPIs (valor/meta/status), top3 riscos e oportunidades, "
        "plano 90 dias, visão 12 meses, e ROI/SROI/VAR/VBI. "
        f"Foco: {focus}. Horizonte: {horizon}. Base:\n{kpis_json}"
    )
    brief_html = gpt5(SYSTEM, brief_prompt)

    scenarios_prompt = (
        "Simule 3 cenários (Conservador, Provável, Agressivo). "
        "Devolva apenas CSV com colunas: "
        "scenario,energy_saving_pct,turnover_delta_pp,capex,carbon_price,ROI_pct,SROI_ratio,VAR_R$,VBI_index. "
        "Use valores plausíveis com base no contexto a seguir:\n" + kpis_json
    )
    scenarios_csv = gpt5(SYSTEM, scenarios_prompt, temperature=0.1)

    brief_html_path = job_dir / "brief.html"
    brief_html_path.write_text(brief_html, encoding="utf-8")
    csv_path = job_dir / "scenarios.csv"
    csv_path.write_text(scenarios_csv, encoding="utf-8")

    base = f"/files/{job_id}"
    return {
        "brief_pdf_url": f"{base}/brief.html",
        "dashboard_url": f"{base}/",
        "benchmark_pdf_url": None,
        "scenarios_csv_url": f"{base}/scenarios.csv",
        "job_id": job_id
    }

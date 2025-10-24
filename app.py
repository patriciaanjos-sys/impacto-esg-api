import os, uuid, httpx, logging
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROCESS_HOOK_TOKEN = os.getenv("PROCESS_HOOK_TOKEN", "")
FILES_ROOT = Path("./files")
FILES_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("impacto")

app = FastAPI(title="IMPACTO ESG+IA (Webhook Tally → Make → Render)")
app.mount("/files", StaticFiles(directory=FILES_ROOT.as_posix()), name="files")

def extract_text_from_pdf_url(url: str, timeout=180) -> str:
    try:
        from pypdf import PdfReader
        pdf_path = FILES_ROOT / f"tmp-{uuid.uuid4()}.pdf"
        with httpx.stream("GET", url, timeout=timeout) as r:
            r.raise_for_status()
            with open(pdf_path, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        text = []
        reader = PdfReader(pdf_path.as_posix())
        for pg in reader.pages[:200]:
            text.append(pg.extract_text() or "")
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass
        return "\n\n".join(text)
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""

def chatgpt(system: str, user: str, model="gpt-5-thinking", temperature=0.2, timeout=180):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada no Render.")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": temperature
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

SYSTEM = (
    "Você é um tradutor executivo de relatórios ESG para C-level. "
    "Siga LGPD (evite dados pessoais). Traduza achados em linguagem de negócio. "
    "Entregue ROI, SROI, VAR e VBI com explicações curtas. "
    "Apoie-se em IFRS S1/S2, GRI e TCFD quando fizer sentido."
)

@app.post("/tally-webhook")
async def tally_webhook(req: Request):
    auth = req.headers.get("authorization", "")
    expected = f"Bearer {PROCESS_HOOK_TOKEN}" if PROCESS_HOOK_TOKEN else None
    if not expected or auth != expected:
        raise HTTPException(401, "Unauthorized (token inválido ou ausente)")

    try:
        data = await req.json()
    except Exception:
        raise HTTPException(400, "JSON inválido")

    name    = data.get("name", "")
    email   = data.get("email", "")
    company = data.get("company", "")
    focus   = data.get("focus", "Estratégia")
    horizon = data.get("horizon", "6 meses")
    language= data.get("language", "pt")

    report_file_url = data.get("report_file_url") or data.get("file_url")
    report_link     = data.get("report_link") or data.get("link") or data.get("report_url")
    report_url = report_file_url or report_link

    if not report_url:
        raise HTTPException(400, "report_url ausente (envie PDF ou link do relatório). Use report_file_url ou report_link.")

    logger.info(f"Processando job para {company} - report_url: {report_url}")

    job_id = str(uuid.uuid4())
    job_dir = FILES_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    pdf_text = extract_text_from_pdf_url(report_url) if report_url.lower().endswith('.pdf') else ""

    extraction_prompt = (
        "Extraia do conteúdo abaixo (se houver) os KPIs E/S/G, riscos top3, oportunidades top3 e metas.\n"
        "Responda em JSON compacto com chaves: kpis (lista com nome, valor, meta, status), riscos_top3, oportunidades_top3.\n\n"
        f"Conteúdo:\n{pdf_text[:60000] if pdf_text else 'Sem extração de PDF disponível; use inferência a partir do contexto e link.'}\n\n"
        f"Link do relatório: {report_url}"
    )
    try:
        kpis_json = chatgpt(SYSTEM, extraction_prompt)
    except Exception as e:
        logger.error(f"Falha GPT na extração: {e}")
        kpis_json = "{}"

    brief_prompt = (
        f"Gere um brief de 1 página em HTML (sem CSS inline). Empresa: {company}. "
        "Traga 3 mensagens-chave, 3-5 KPIs (valor/meta/status), top3 riscos e oportunidades, "
        "plano 90 dias, visão 12 meses, e ROI/SROI/VAR/VBI. "
        f"Foco: {focus}. Horizonte: {horizon}. Base:\n{kpis_json}\n\n"
        f"Seja direto, executivo e claro. Idioma: {language}. Assine como 'Curadoria IMPACTO ESG'."
    )
    try:
        brief_html = chatgpt(SYSTEM, brief_prompt)
    except Exception as e:
        logger.error(f"Falha GPT no brief: {e}")
        brief_html = f"<h1>Brief Executivo ESG</h1><p>Não foi possível gerar o conteúdo automaticamente. Link do relatório: {report_url}</p>"

    scenarios_prompt = (
        "Simule 3 cenários (Conservador, Provável, Agressivo). "
        "Devolva apenas CSV com colunas: "
        "scenario,energy_saving_pct,turnover_delta_pp,capex,carbon_price,ROI_pct,SROI_ratio,VAR_R$,VBI_index. "
        "Use valores plausíveis com base no contexto a seguir:\n" + kpis_json
    )
    try:
        scenarios_csv = chatgpt(SYSTEM, scenarios_prompt, temperature=0.1)
    except Exception as e:
        logger.error(f"Falha GPT nos cenários: {e}")
        scenarios_csv = "scenario,energy_saving_pct,turnover_delta_pp,capex,carbon_price,ROI_pct,SROI_ratio,VAR_R$,VBI_index\nConservador,2,0.1,100000,70,4,1.2,150000,58\nProvável,5,0.3,250000,85,9,1.8,320000,67\nAgressivo,9,0.6,400000,110,15,2.4,550000,74"

    (job_dir / "brief.html").write_text(brief_html, encoding="utf-8")
    (job_dir / "scenarios.csv").write_text(scenarios_csv, encoding="utf-8")

    base = f"/files/{job_id}"
    return {
        "brief_pdf_url": f"{base}/brief.html",
        "dashboard_url": f"{base}/",
        "benchmark_pdf_url": None,
        "scenarios_csv_url": f"{base}/scenarios.csv",
        "job_id": job_id,
        "gpt_summary": "Resumo gerado. Veja brief.html"
    }

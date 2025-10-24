IMPACTO ESG+IA (MVP) — API para Tally/Make

Variáveis no Render:
- OPENAI_API_KEY: sua chave da OpenAI
- PROCESS_HOOK_TOKEN: ex.: impacto123

Endpoint:
POST /tally-webhook
Header: Authorization: Bearer <PROCESS_HOOK_TOKEN>

Body JSON esperado (um OU outro campo de relatório):
{
  "name": "...",
  "email": "...",
  "company": "...",
  "report_file_url": "https://...pdf",   // upload do Tally (opcional)
  "report_link": "https://...link",      // link colado (opcional)
  "focus": "Estratégia",
  "horizon": "6 meses",
  "language": "pt"
}

A API gera /files/<job_id>/brief.html e scenarios.csv e retorna os links.

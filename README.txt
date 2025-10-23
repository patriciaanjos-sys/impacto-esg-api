IMPACTO ESG+IA (MVP simples)

Arquivos:
- app.py              → cérebro (entende o relatório e gera as saídas)
- requirements.txt    → o que precisa instalar
- render.yaml         → ensina o Render a ligar tudo

Como usar:
1) Crie conta em https://render.com
2) Envie esta pasta (via GitHub ou Upload do ZIP) como Blueprint (lê o render.yaml).
3) Ao criar o serviço, preencha as variáveis:
   - OPENAI_API_KEY (sua chave da OpenAI)
   - PROCESS_HOOK_TOKEN (uma senha sua, ex.: impacto123)
4) Depois do deploy, use a URL:
   https://SEU-SERVICE.onrender.com/tally-webhook
5) Coloque essa URL no Make (HTTP POST) com header:
   Authorization: Bearer PROCESS_HOOK_TOKEN

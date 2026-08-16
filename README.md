# Moldura Deoclécio Duarte 44222

Aplicação Flask + PostgreSQL + Volume para Railway. O visitante envia uma foto, ajusta posição/zoom no navegador, aplica a moldura e baixa o PNG final. O painel admin gerencia filtros, acompanha métricas e visualiza/remover envios.

## Railway
1. Crie um projeto no GitHub com estes arquivos.
2. No Railway, adicione **PostgreSQL**.
3. Adicione um **Volume** montado em `/data`.
4. Defina as variáveis do `.env.example` (o Railway injeta `DATABASE_URL` automaticamente ao vincular o Postgres).
5. Deploy. O app cria as tabelas e o filtro inicial automaticamente.
6. Acesse `/admin/login` com `ADMIN_EMAIL` e `ADMIN_PASSWORD`.

## Variáveis principais
- `SECRET_KEY`: chave longa e aleatória.
- `DATA_DIR=/data`: caminho do volume persistente.
- `ADMIN_EMAIL` e `ADMIN_PASSWORD`: admin inicial.
- `RETENTION_DAYS`: retenção automática de fotos; padrão 30 dias.
- `MAX_UPLOAD_MB`: tamanho máximo de upload; padrão 15 MB.

## Privacidade
O visitante precisa aceitar explicitamente o armazenamento temporário da foto para gerar a moldura. O admin pode apagar um envio individualmente, e o sistema remove automaticamente arquivos vencidos conforme a retenção configurada.

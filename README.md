# concurso-notifier

Bot de Telegram que monitora concursos públicos abertos no Brasil e avisa o
usuário quando aparece algo nos estados e filtros que ele escolheu.

Os dados vêm do [acheconcursos.com.br](https://www.acheconcursos.com.br),
raspados periodicamente e guardados em SQLite.

## Comandos

| Comando | O que faz |
| --- | --- |
| `/start` | Registra o usuário e mostra as boas-vindas. |
| `/uf RJ SP` | Define os estados de interesse. Sem argumentos, mostra os atuais. |
| `/concursos` | Envia os concursos abertos que o usuário ainda não recebeu. |
| `/todos` | Lista todos os concursos abertos nos estados escolhidos. |
| `/config` | Menu inline: salário mínimo, nível, vagas mínimas e liga/desliga notificações. |
| `/help` | Guia dos comandos. |

Em paralelo, duas tarefas rodam sozinhas: uma atualiza a base de concursos
(padrão: a cada 61 min) e outra envia os alertas pendentes (a cada 17 min).

## Como rodar

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # preencha o TELEGRAM_TOKEN
python main.py
```

O banco `concursos.db` é criado e migrado sozinho na primeira execução.

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```

Cobrem os parsers, os filtros de busca, o controle de envios, a montagem das
mensagens, o parser do HTML e a migração de um banco no esquema antigo.
Nenhum teste faz rede nem toca no banco de produção.

## Estrutura

```
main.py           registro de handlers, agendador e error handler
config.py         .env, logging, tabela de siglas/slugs dos estados
db.py             SQLite: esquema, migrações e todas as queries
scrapping.py      coleta no site de origem (síncrona + wrapper async)
bot/handlers.py   /start /help /uf /concursos /todos
bot/menu_config.py  /config e os callbacks dos botões inline
bot/jobs.py       tarefas periódicas de scraping e envio
bot/formatacao.py montagem e agrupamento das mensagens
tests/            suíte pytest (sem rede, banco temporário)
```

## Notas de implementação

**Scraping fora do event loop.** `scrapping.py` é bloqueante de propósito
(`requests` + `time.sleep` entre estados, para não martelar a origem). Dentro
do bot ele só é usado via `coletar_concursos()`, que despacha para uma thread
— rodar a varredura dos 27 estados no event loop deixava o bot mudo por
minutos a cada ciclo.

**Colunas normalizadas.** O site entrega tudo como texto (`"R$ 13.288,85"`,
`"13/02/2026"`, `"-"`). Além do texto original, cada concurso guarda
`inscricoes_ate_iso`, `salario_num` e `vagas_num`, usados para filtrar e
ordenar. Sem isso os filtros mentem: `CAST('R$ 13.288,85' AS INTEGER)` é `0`
e, na ordem de tipos do SQLite, o texto `'-'` é maior que qualquer inteiro.

**Migrações.** O esquema é versionado na tabela `schema_version` e
`criar_tabelas()` aplica o que faltar, de forma idempotente, a cada boot.

**Entrega.** Um concurso só é marcado como enviado depois que a mensagem sai
de fato, e as mensagens são agrupadas (com teto por ciclo) para respeitar o
limite de ~1 msg/s por chat da API do Telegram.

## Limitações conhecidas

- Depende do HTML do acheconcursos.com.br; mudança de layout quebra o parser.
- Os concursos expirados continuam no banco (são filtrados na leitura, não
  removidos). Não incomoda no volume atual, mas cresce indefinidamente.
- Sem testes automatizados.

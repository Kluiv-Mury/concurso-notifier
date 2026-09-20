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
| `/deletar` | Apaga todos os dados do usuário. Pede confirmação. |
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

## Dados e privacidade

O bot guarda, por usuário: o `chat_id`, o primeiro nome do Telegram, os
estados de interesse, os filtros configurados e quais concursos já foram
enviados (para não repetir).

O nome é gravado **cifrado** (Fernet, chave em `NOME_KEY`). Sem chave
configurada, ele simplesmente não é guardado — o padrão falha na direção da
privacidade. O `chat_id` fica legível por necessidade: é a chave de busca e o
endereço de envio.

`/deletar` apaga tudo isso, com confirmação. Bloquear o bot só interrompe as
mensagens — os dados continuariam no banco, então este é o caminho para sair
de verdade.

Nada é compartilhado com terceiros e o bot não lê mensagens fora dos próprios
comandos.

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

**Backup.** Uma cópia do banco é gravada no boot e a cada 24h em `backups/`,
mantendo as 7 mais recentes. Usa a API `Connection.backup()` do SQLite, que é
consistente com o banco em uso. Os backups ficam no mesmo disco: isso protege
contra corrupção de arquivo, não contra o disco falhar.

**Saúde do scraping.** A origem mudar de layout é a falha mais provável e a
mais silenciosa: o parser devolveria vazio para os 27 estados, igual a um dia
sem concurso aberto. Por isso `concursos_ache_conc` distingue "a página não
veio" (`None`) de "veio e nada foi extraído" (`[]`), e cada ciclo é
classificado. O aviso vai para o log e, se `ADMIN_CHAT_ID` estiver
configurado, para o Telegram.

**Cifra do nome.** `nome` é o único campo pessoal que dá para cifrar sem
quebrar nada: nunca entra em `WHERE`, `ORDER BY` nem `JOIN`. Como a chave mora
no `.env`, ao lado do banco, isso protege os casos em que o banco vaza *sem* o
`.env` junto — um backup sincronizado para fora, ou o arquivo indo parar onde
não devia. Contra quem tem o servidor inteiro não protege, e nem tenta; para
isso vale criptografia de disco no host.

A conversão de nomes ainda em texto puro roda a cada boot, não como migração
de uma vez só: a chave pode ser configurada depois, e aí os registros antigos
precisam ser convertidos naquele momento.

**Scraping educado.** O `robots.txt` da origem permite as páginas usadas. O
User-Agent identifica o bot em vez de imitar um navegador, e há pausa entre
estados.

## Limitações conhecidas

- Depende do HTML do acheconcursos.com.br; mudança de layout quebra o parser.
- Os concursos expirados continuam no banco (são filtrados na leitura, não
  removidos). Não incomoda no volume atual, mas cresce indefinidamente.
- Os backups ficam no mesmo disco do banco, e backups feitos antes de
  `NOME_KEY` ser configurada contêm os nomes em texto puro.
- Perder a `NOME_KEY` torna os nomes já gravados ilegíveis. Não é crítico
  (nada depende deles hoje), mas é irreversível.
- `date('now','localtime')` usa o fuso da máquina. Num servidor em UTC, o
  corte de prazo acontece 3h mais cedo que o esperado no Brasil — defina
  `TZ=America/Sao_Paulo` no ambiente antes de subir para um host.
- Sem CI: os testes só rodam se alguém lembrar.

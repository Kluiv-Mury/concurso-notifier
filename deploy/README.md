# Rodar o bot como serviço

`python main.py` num terminal morre quando o terminal fecha, quando a máquina
reinicia, quando você faz logoff ou quando o processo crasha — e nada o levanta
de volta.

Não é hipótese: esta instalação parou em **19/04/2026** e só se percebeu em
setembro, cinco meses depois. O banco não era escrito desde então e nenhum dos
usuários recebeu nada nesse período.

Um supervisor resolve isso: garante que o processo esteja de pé e o reinicia
quando cai.

---

## Linux (VPS, servidor)

Use o [`concurso-notifier.service`](concurso-notifier.service) deste diretório.

```bash
sudo cp deploy/concurso-notifier.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now concurso-notifier
```

Ajuste antes o `User`, o `WorkingDirectory` e o `ExecStart` para os caminhos
reais da sua máquina.

Verificar e acompanhar:

```bash
systemctl status concurso-notifier
journalctl -u concurso-notifier -f
```

A linha que importa é `Restart=always`: crashou, volta em 10 segundos;
rebootou, sobe junto com o sistema.

---

## Windows

### Opção A — NSSM (recomendada)

O [NSSM](https://nssm.cc/) transforma qualquer executável num serviço do
Windows de verdade, com reinício automático e log em arquivo.

```powershell
nssm install ConcursoNotifier "C:\caminho\notifier\Scripts\python.exe" "C:\caminho\main.py"
nssm set ConcursoNotifier AppDirectory "C:\caminho\concurso-notifier"
nssm set ConcursoNotifier AppStdout "C:\caminho\logs\bot.log"
nssm set ConcursoNotifier AppStderr "C:\caminho\logs\bot.log"
nssm set ConcursoNotifier Start SERVICE_AUTO_START
nssm start ConcursoNotifier
```

Por padrão o NSSM já reinicia o processo quando ele termina. Para conferir o
estado: `nssm status ConcursoNotifier`.

### Opção B — Agendador de Tarefas

Sem instalar nada, mas com três opções que precisam estar marcadas, senão não
resolve o problema:

1. **Gatilho:** "Ao iniciar o computador" — sobe sem precisar de login.
2. **Geral:** "Executar estando o usuário conectado ou não" — sobrevive ao
   logoff.
3. **Configurações:** "Se a tarefa falhar, reiniciar a cada 1 minuto", com
   algumas tentativas — é o equivalente ao `Restart=always`.

Na aba Ações, o programa é o `python.exe` da venv e o argumento é o
`main.py`, com "Iniciar em" apontando para a pasta do projeto.

---

## Depois de subir

O bot avisa sozinho quando o scraping quebra, mas só se você disser para quem.
Configure o `ADMIN_CHAT_ID` no `.env` — sem ele o aviso fica apenas no log,
que é exatamente onde ninguém olha.

Confira também que as tarefas periódicas realmente engataram: nos primeiros
minutos o log deve mostrar o backup e o resumo do ciclo de scraping.

```
Backup em concursos-AAAAMMDD-HHMMSS.db (...); 0 antigo(s) removido(s).
Fim do scraping. 24 estados com dados, 3 vazios, 0 inacessíveis; ...
```

Se nada disso aparecer, o `Application.job_queue` provavelmente está `None` —
sinal de que as dependências foram instaladas sem o extra `[job-queue]`.

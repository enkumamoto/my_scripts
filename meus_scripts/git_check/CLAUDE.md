# CLAUDE.md

Contexto para trabalhar (IA ou humano) no `git_check`, o painel web local de checagem dos repositórios do GitHub. Este arquivo vale só para esta pasta; o `CLAUDE.md` da raiz do repositório não trata deste script.

## O que é

Um único arquivo Python (`git_check.py`) que sobe um servidor FastAPI em `127.0.0.1` e serve **uma página só** (HTML/CSS/JS embutidos na constante `PAGINA`). A página:

1. lista os repositórios do usuário, separados em **públicos** e **privados**;
2. checa 9 regras em cada repositório **público** (descrição, README, licença, `.gitignore`, branch protegida, sem force push, secret scanning, push protection, Dependabot);
3. troca a visibilidade (público ⇄ privado), com confirmação digitando o nome do repo;
4. tem um menu lateral que corrige pendências: adicionar `.gitignore`, descrição, README.md, licença, regras (ruleset de `Pull_Requests-2.json` + secret scanning) e ativar alertas do Dependabot.

Roda na máquina do usuário (macOS), não em servidor. Uso detalhado em `README.md`; catálogo de regras e runbook de erros em `.claude/SKILLS.md`.

## Estrutura

```
git_check/
├── git_check.py           # servidor FastAPI + pagina HTML/JS embutida (arquivo unico)
├── Pull_Requests-2.json   # ruleset aplicado aos repos publicos (export do GitHub)
├── requirements.txt       # fastapi, uvicorn, httpx, watchfiles
├── README.md              # uso para o usuario final
├── CLAUDE.md              # este arquivo
└── .claude/SKILLS.md      # catalogo das regras + runbook de erros da API
```

`.venv/` local é do usuário (ignorado pelo `.gitignore` da raiz) — não apagar nem instalar pacotes nele.

## Rodar

```bash
cd meus_scripts/git_check
pip install -r requirements.txt
python3 git_check.py                  # http://127.0.0.1:8000, abre o navegador
python3 git_check.py --porta 8765 --sem-navegador
python3 git_check.py --sem-recarga    # sem auto-atualizacao
```

Token do GitHub: `GITHUB_TOKEN`/`GH_TOKEN` ou, na falta, `gh auth token`. Precisa do escopo `repo`.

## Organização do `git_check.py`

| Parte | Onde | Função |
| --- | --- | --- |
| Configuração | constantes no topo (`HOST`, `PORTA`, `AFILIACAO`, `ARQUIVO_RULESET`) | tudo que o usuário ajusta |
| Cliente GitHub | `gh()`, `exigir()`, `mensagem_erro()`, `caminho_repo()` | chamadas à API, validação de status e de nome de repo |
| Checagem de regras | `checar_regras()` + `regras_de_branch()`, `regras_de_seguranca()`, `por_status()` | monta a lista de regras `{nome, estado, detalhe}` |
| Ações | `adicionar_arquivo()`, `acao_*()`, `carregar_ruleset()` | escrita no GitHub (um repositório por chamada) |
| Página | `PAGINA` (string `r"""..."""`) | HTML + CSS + JS; `__TOKEN__` é trocado pelo token da execução |
| Entrada | `main()` | argparse, valida o token, `uvicorn.run` (com `reload=True` por padrão) |

Rotas: `GET /`, `GET /api/execucao`, `GET /api/repos`, `GET /api/regras/{dono}/{nome}`, `GET /api/modelos`, `POST /api/visibilidade`, `POST /api/acoes/{descricao,gitignore,readme,licenca,regras,dependabot}`.

No JS, cada botão do menu lateral é uma entrada do objeto `ACOES` (`titulo`, `ajuda`, `regras` = nomes das regras que definem a pendência, `opcoes()`, `controle(r)`, `corpo(r, linha)`). O diálogo é genérico: lista os repos de `pendentes(chave)` e chama `POST /api/acoes/<chave>` linha a linha.

## Testar (sem escrever no GitHub)

**Nunca execute ações de escrita contra os repositórios reais do usuário para testar** (PATCH de visibilidade/descrição, PUT de arquivo, POST de ruleset, PUT do Dependabot). Teste só leitura e recusas que acontecem antes de qualquer escrita.

```bash
# venv descartavel fora da pasta (nao usar o .venv do usuario)
python3 -m venv /tmp/gc && /tmp/gc/bin/pip install -q -r requirements.txt
/tmp/gc/bin/python git_check.py --porta 8765 --sem-navegador --sem-recarga &

B=http://127.0.0.1:8765
T=$(curl -s $B/ | grep -o 'const TOKEN = "[^"]*"' | cut -d'"' -f2)
curl -s -H "X-Painel-Token: $T" $B/api/repos
curl -s -H "X-Painel-Token: $T" $B/api/regras/<dono>/<repo>
curl -s -H "X-Painel-Token: $T" $B/api/modelos

# sintaxe do JS embutido
node -e 'const s=require("fs").readFileSync("git_check.py","utf8");new Function(s.match(/<script>([\s\S]*?)<\/script>/)[1])'
```

Recusas seguras para testar (não chegam a escrever): nome inválido (`../user` → 422), sem token (403), `Host` forjado (400), modelo/licença desconhecidos (422), arquivo que já existe (409), regras em repo privado (422), nenhuma opção marcada (422), `Pull_Requests-2.json` inválido (500 — restaure o arquivo depois).

Cada carregamento da página faz ~6 chamadas por repo público (~200 no total); o limite é 5000/h. Confira com `gh api rate_limit`.

## Convenções

- Identificadores, mensagens da API e comentários em português **sem acento** (`descricao`, `licenca`); texto da interface em português **com acento**.
- Estados de regra: `ok` (✓), `falha` (✗) e `nd` (? — a API não informou, ex.: sem admin). Só `falha` conta como pendência.
- Os nomes das regras (`"Descricao"`, `"README"`, `".gitignore"`, `"Branch protegida"`...) são a chave que liga backend, contadores e `ACOES[*].regras` no JS — renomear exige mudar nos dois lados.
- Todo texto dinâmico inserido no HTML passa por `esc()`.
- Comentários escassos, só onde o porquê não é óbvio.

## Decisões técnicas (não regredir)

- **Segurança local:** servidor só em `127.0.0.1`; `TrustedHostMiddleware` (`127.0.0.1`/`localhost`) contra DNS rebinding; todas as rotas `/api/*` exigem o cabeçalho `X-Painel-Token` com o token gerado a cada execução (`TOKEN_PAGINA`). O cabeçalho customizado força preflight CORS, então outro site aberto no navegador não consegue acionar escrita.
- **Validação de nome de repo** em `caminho_repo()`: cada parte casa `[A-Za-z0-9_.-]+` e não pode ser `.` nem `..`. Sem isso, `../user` vira `PATCH /user` (já aconteceu em teste). Toda rota que monta `/repos/...` deve passar por ela. Modelos de `.gitignore` e chaves de licença são validados contra o catálogo do GitHub antes de entrar na URL.
- **Regras só para repositórios públicos.** Privados não são checados nem recebem regras; `acao_regras` recusa repo privado no servidor, além do filtro na página.
- **Ruleset vem de `Pull_Requests-2.json`**, relido a cada uso (sem reiniciar). Os campos somente leitura do export (`id`, `source`, `source_type`, ...) são descartados; só `name`, `target`, `enforcement`, `conditions`, `rules`, `bypass_actors` vão para a API. Não voltar a montar o ruleset em código.
- **Aplicar só o que está pendente:** em "Adicionar regras", cada repo recebe ruleset apenas se `Branch protegida` ou `Sem force push` estiver em falha, e secret scanning/push protection apenas se estiverem em falha — evita ruleset duplicado.
- **Nunca sobrescrever arquivos:** `adicionar_arquivo()` checa se o caminho existe e devolve 409 antes do PUT.
- **Branch padrão protegida:** se o PUT direto for recusado por *rule violation* (409), o arquivo vai para uma branch `git-check/<arquivo>` e um PR é aberto. O ruleset atual tem bypass de admin, então normalmente o commit direto passa.
- **Ações destrutivas/externas pedem confirmação explícita:** troca de visibilidade exige digitar o nome do repo; nas ações do menu as linhas vêm desmarcadas e "Marcar todos" é opt-in. Botões ficam desabilitados para forks, arquivados e repos sem admin.
- **Dependabot:** o botão liga só os alertas; *security updates* é opcional e vem desmarcado (abre PRs nos repos). *Version updates* ficam de fora por decisão do usuário.
- **Auto-atualização:** sem `--sem-recarga`, `main()` roda `uvicorn.run("git_check:app", reload=True, reload_dirs=[pasta do script])` — o uvicorn importa o módulo pelo nome, então tudo que o app precisa deve estar em nível de módulo (não dentro de `main()`). Cada (re)início gera `ID_EXECUCAO` e `TOKEN_PAGINA` novos; a página faz polling em `/api/execucao` (timeout de 2 s, sem sobreposição) e recarrega quando o ID muda — isso também resolve o token antigo. `/api/execucao` fica sem token de propósito: só expõe um ID aleatório. `watchfiles` é obrigatório: sem ele o uvicorn cai no `StatReload`, que varreria o `.venv` inteiro a cada 0,25 s; `reload_excludes` não aceita caminho absoluto (o uvicorn quebra), por isso não é usado.
- **Sem geração por IA:** descrição é digitada pelo usuário e o README sai do modelo editável. A geração com o Claude (API da Anthropic) foi implementada e removida a pedido do usuário — não reintroduzir sem pedido explícito.
- **Arquivo único**, sem build e sem framework de front-end; dependências só `fastapi`, `uvicorn`, `httpx`, `watchfiles`.

## Como estender

**Nova regra checada:** adicione a chamada no `asyncio.gather` de `checar_regras()` e um `regra(nome, estado, detalhe)` na lista. Se ela tiver correção pelo menu, inclua o nome em `ACOES[<chave>].regras`. Documente em `README.md` e em `.claude/SKILLS.md`.

**Nova ação no menu lateral:**

1. Modelo `class AcaoX(Acao)` + rota `POST /api/acoes/x` usando `acao.base()` e `exigir()`; retorne `{"mensagem": ..., "url": ...}`.
2. Botão `<button data-acao="x">... <span class="cont zero" id="cont-x">–</span></button>` no `<aside>`.
3. Entrada `x` em `ACOES` no JS.
4. Linha na tabela do menu em `README.md` e no catálogo do `.claude/SKILLS.md`.

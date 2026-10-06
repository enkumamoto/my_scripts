# git_check

Painel web local (FastAPI) para checar os repositórios do GitHub, tudo em uma página só: lista públicos e privados separadamente, checa regras dos públicos, corrige as pendências por um menu lateral e permite trocar a visibilidade (público ⇄ privado).

## Uso

```bash
cd meus_scripts/git_check
python3 -m venv .venv && source .venv/bin/activate   # opcional, mas recomendado
pip install -r requirements.txt

python3 git_check.py                           # sobe em http://127.0.0.1:8000 e abre o navegador
python3 git_check.py --porta 9000              # outra porta
python3 git_check.py --sem-navegador           # nao abre o navegador
python3 git_check.py --sem-recarga             # desliga a auto-atualizacao
```

Sem `.venv` (Python do Homebrew, que bloqueia `pip install` direto — PEP 668):

```bash
/usr/bin/env python3 -m pip install --user --break-system-packages -r requirements.txt
```

Autenticação: usa `GITHUB_TOKEN`/`GH_TOKEN` se definido; senão, o token do `gh auth token` (GitHub CLI logado). O token precisa do escopo `repo`.

Regras checadas em cada repositório público (passe o mouse sobre a etiqueta para ver o detalhe):

| Regra | Passa quando |
| --- | --- |
| Descricao | o repositório tem descrição |
| README / Licenca | o GitHub reconhece os arquivos (community profile) |
| .gitignore | existe `.gitignore` na raiz |
| Branch protegida | a branch padrão tem proteção clássica ou ruleset ativo |
| Sem force push | force push bloqueado na branch padrão |
| Secret scanning / Push protection | recursos ativados no repositório |
| Dependabot | alertas de vulnerabilidade ativados |

`✓` passou, `✗` pendente, `?` a API não informou (ex.: sem permissão de admin).

## Menu lateral: corrigir pendências

Cada botão abre um diálogo com os repositórios **públicos** que têm aquela pendência (o número ao lado do botão). Nada é aplicado sem marcar a linha do repositório e clicar em "Aplicar nos marcados"; o resultado aparece linha a linha, com link para o commit/ruleset.

| Botão | O que faz |
| --- | --- |
| Adicionar .gitignore | commita um `.gitignore` a partir dos modelos do GitHub; o modelo vem sugerido pela linguagem do repositório |
| Adicionar Descrição | grava a descrição digitada para cada repositório |
| Adicionar README.md | commita um `README.md` inicial a partir de um modelo editável (`{nome}` e `{descricao}` são substituídos) |
| Adicionar Licença | commita um `LICENSE` (licenças do GitHub: MIT, Apache-2.0, GPL-3.0...) com o ano atual e o titular informado |
| Adicionar regras ao repo público | aplica na branch padrão o ruleset definido em `Pull_Requests-2.json` e ativa secret scanning / push protection |
| Ativar alertas do Dependabot | liga os alertas de vulnerabilidade em dependências; opcionalmente (desmarcado por padrão) liga também os security updates, que abrem PRs de correção |

Detalhes:

- Arquivos nunca são sobrescritos: se `.gitignore`, `README.md` ou `LICENSE` já existir, a linha retorna erro e nada é alterado.
- O commit vai direto na branch padrão. Se um ruleset bloquear o push direto (sem bypass de admin), o arquivo é commitado em uma branch `git-check/...` e um pull request é aberto.
- Em "Adicionar regras", cada repositório recebe só o que está pendente nele — quem já tem ruleset não ganha outro. Repositórios privados não recebem regras (o botão só lista públicos e o servidor recusa privados).
- README e licença são detectados pelo GitHub com algum atraso: logo após o commit a etiqueta pode continuar `✗` por alguns minutos; use "Recarregar".
- Repositórios arquivados ou sem permissão de admin não entram nas listas.

Troca de visibilidade: botão na última coluna de cada linha; pede para digitar o nome do repositório antes de confirmar. Fica desabilitado para forks, repositórios arquivados e repositórios sem permissão de admin. **Tornar público expõe todo o histórico de commits; tornar privado perde stars/watchers.**

Por padrão lista apenas repositórios dos quais você é dono (constante `AFILIACAO` no topo do arquivo). O servidor escuta só em `127.0.0.1` e a API exige um token gerado a cada execução e embutido na página, para que outros sites abertos no navegador não consigam acionar a troca de visibilidade.

## Arquivos

```
git_check/
├── git_check.py       # servidor FastAPI + pagina HTML/JS embutida (arquivo unico)
├── requirements.txt   # fastapi, uvicorn, httpx, watchfiles
├── Pull_Requests-2.json  # ruleset aplicado aos repos publicos
└── README.md          # este arquivo
```

## Configuração

Constantes no topo de `git_check.py`:

| Constante | Uso |
| --- | --- |
| `HOST` / `PORTA` | endereço e porta locais (padrão `127.0.0.1:8000`; a porta também aceita `--porta`) |
| `ARQUIVO_RULESET` | JSON do ruleset aplicado pelo botão "Adicionar regras" (padrão `Pull_Requests-2.json`, na mesma pasta) |
| `AFILIACAO` | quais repositórios listar: `owner` (padrão), ou incluir `collaborator` / `organization_member` |

## Rotas

| Rota | Função |
| --- | --- |
| `GET /` | a página única |
| `GET /api/repos` | lista os repositórios (públicos e privados) |
| `GET /api/regras/{dono}/{nome}` | checa as regras de um repositório |
| `POST /api/visibilidade` | troca a visibilidade (`{"full_name": "dono/nome", "privado": true}`) |
| `GET /api/execucao` | ID da execução do servidor (usado pela auto-atualização; não exige token) |
| `GET /api/modelos` | modelos de `.gitignore` e licenças disponíveis no GitHub |
| `POST /api/acoes/{descricao,gitignore,readme,licenca,regras,dependabot}` | ações do menu lateral, um repositório por chamada |

As rotas `/api/*` exigem o cabeçalho `X-Painel-Token`, que a própria página envia.

## Ruleset dos repositórios públicos

O botão "Adicionar regras ao repo público" cria o ruleset descrito em `Pull_Requests-2.json` (hoje: bloquear exclusão e force push na branch padrão, exigir pull request, admin pode ignorar). O arquivo é o JSON exportado pelo GitHub (Settings → Rules → Rulesets → Export); os campos somente leitura do export (`id`, `source`, `source_type`) são descartados. O arquivo é relido a cada uso — para mudar as regras, edite ou substitua o JSON e clique em "Recarregar".

## Auto-atualização

Por padrão o servidor roda com recarga automática: ao salvar `git_check.py`, o uvicorn reinicia o servidor (via `watchfiles`) e a página aberta no navegador se recarrega sozinha em cerca de 1 s. A página consulta `/api/execucao` a cada segundo; quando o ID muda, ela recarrega.

- Se o código salvo tiver erro de sintaxe, o traceback aparece no terminal e a página fica como está; ao corrigir e salvar, tudo volta sozinho.
- O recarregamento perde o filtro digitado e fecha diálogos abertos — evite salvar o código no meio de uma ação em lote.
- `--sem-recarga` desliga o reinício automático do servidor. A página continua se recarregando se você reiniciar o script na mão.
- Mudanças no `Pull_Requests-2.json` não reiniciam o servidor (o arquivo é relido a cada uso); clique em "Recarregar".

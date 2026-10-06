#!/usr/bin/env python3
"""Painel web local (FastAPI) para checar os repositorios do GitHub.

Lista repos publicos e privados separadamente, checa regras dos publicos
(descricao, README, licenca, .gitignore, protecao de branch, secret scanning,
Dependabot) e permite trocar a visibilidade. Tudo em uma pagina so.

Uso: python3 git_check.py [--porta 8000] [--sem-navegador] [--sem-recarga]
Token: variavel GITHUB_TOKEN/GH_TOKEN ou, na falta, `gh auth token`.
"""

import argparse
import asyncio
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import quote

try:
    import httpx
    import uvicorn
    import watchfiles  # noqa: F401  (usado pelo reload do uvicorn)
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.responses import HTMLResponse, PlainTextResponse
    from pydantic import BaseModel, Field
    from starlette.middleware.trustedhost import TrustedHostMiddleware
except ImportError as e:
    sys.exit(
        f"Erro: dependencia nao instalada ({e.name}). Instale com:\n"
        "  python3 -m pip install -r requirements.txt"
    )

# ----------------------------- CONFIGURACAO -----------------------------
HOST = "127.0.0.1"
PORTA = 8000
API = "https://api.github.com"
AFILIACAO = "owner"  # owner | owner,organization_member | owner,collaborator,organization_member
ARQUIVO_RULESET = Path(__file__).with_name("Pull_Requests-2.json")  # ruleset aplicado aos repos publicos
PADRAO_NOME = re.compile(r"[A-Za-z0-9_.-]+")
# ------------------------------------------------------------------------

TOKEN_PAGINA = secrets.token_urlsafe(32)
ID_EXECUCAO = secrets.token_hex(8)  # muda a cada (re)inicio; a pagina recarrega quando muda


def obter_token():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        saida = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        saida = None
    if saida and saida.returncode == 0 and saida.stdout.strip():
        return saida.stdout.strip()
    raise RuntimeError(
        "token do GitHub nao encontrado. Defina GITHUB_TOKEN ou rode `gh auth login`."
    )


@asynccontextmanager
async def ciclo_de_vida(app):
    app.state.http = httpx.AsyncClient(
        base_url=API,
        timeout=20,
        headers={
            "Authorization": f"Bearer {obter_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    yield
    await app.state.http.aclose()


def exigir_token(x_painel_token: str = Header(default="")):
    if not secrets.compare_digest(x_painel_token, TOKEN_PAGINA):
        raise HTTPException(403, "token da pagina invalido; recarregue a pagina")


app = FastAPI(title="git_check", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


async def gh(metodo, caminho, **kw):
    try:
        return await app.state.http.request(metodo, caminho, **kw)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"falha ao falar com o GitHub: {e}") from e


def caminho_repo(dono, nome):
    for parte in (dono, nome):
        if not PADRAO_NOME.fullmatch(parte) or parte in (".", ".."):
            raise HTTPException(422, f"nome de repositorio invalido: {dono}/{nome}")
    return f"/repos/{dono}/{nome}"


def exigir(r, *codigos):
    if r.status_code not in codigos:
        raise HTTPException(r.status_code, mensagem_erro(r))
    return r.json() if r.content else None


def mensagem_erro(r):
    try:
        corpo = r.json()
    except ValueError:
        return r.text[:200] or f"HTTP {r.status_code}"
    msg = corpo.get("message", f"HTTP {r.status_code}")
    detalhes = "; ".join(
        e.get("message", "") if isinstance(e, dict) else str(e)
        for e in corpo.get("errors", [])
    )
    return f"{msg} ({detalhes})" if detalhes else msg


def resumo(repo):
    return {
        "nome": repo["name"],
        "full_name": repo["full_name"],
        "url": repo["html_url"],
        "descricao": repo.get("description") or "",
        "privado": repo["private"],
        "fork": repo["fork"],
        "arquivado": repo["archived"],
        "linguagem": repo.get("language") or "",
        "ultimo_push": repo.get("pushed_at"),
        "admin": bool(repo.get("permissions", {}).get("admin")),
    }


def regra(nome, estado, detalhe=""):
    return {"nome": nome, "estado": estado, "detalhe": detalhe}


def por_status(nome, r, ok, falha):
    if r.status_code in (200, 204):
        return regra(nome, "ok", ok)
    if r.status_code == 404:
        return regra(nome, "falha", falha)
    return regra(nome, "nd", mensagem_erro(r))


def regras_de_branch(branch, protecao, rulesets):
    classica = protecao.json() if protecao.status_code == 200 else None
    tipos = (
        sorted({r["type"] for r in rulesets.json()})
        if rulesets.status_code == 200
        else []
    )
    conhecido = protecao.status_code in (200, 404) and rulesets.status_code in (200, 404)

    origem = []
    if classica:
        origem.append("protecao classica")
    if tipos:
        origem.append("ruleset: " + ", ".join(tipos))
    if origem:
        protegida = regra("Branch protegida", "ok", f"{branch}: " + " + ".join(origem))
    elif conhecido:
        protegida = regra("Branch protegida", "falha", f"{branch} sem protecao nem ruleset")
    else:
        protegida = regra("Branch protegida", "nd", mensagem_erro(protecao))

    sem_force = "non_fast_forward" in tipos or (
        classica is not None
        and not classica.get("allow_force_pushes", {}).get("enabled", False)
    )
    if sem_force:
        force = regra("Sem force push", "ok", f"force push bloqueado em {branch}")
    elif conhecido:
        force = regra("Sem force push", "falha", f"force push liberado em {branch}")
    else:
        force = regra("Sem force push", "nd", mensagem_erro(protecao))
    return [protegida, force]


def regras_de_seguranca(repo):
    analise = repo.get("security_and_analysis")
    saida = []
    for nome, chave in (
        ("Secret scanning", "secret_scanning"),
        ("Push protection", "secret_scanning_push_protection"),
    ):
        if analise is None or chave not in analise:
            saida.append(regra(nome, "nd", "nao informado pela API (exige admin)"))
        else:
            status = analise[chave].get("status")
            saida.append(regra(nome, "ok" if status == "enabled" else "falha", str(status)))
    return saida


@app.get("/api/repos", dependencies=[Depends(exigir_token)])
async def listar_repos():
    usuario = await gh("GET", "/user")
    if usuario.status_code != 200:
        raise HTTPException(usuario.status_code, mensagem_erro(usuario))

    repos, pagina = [], 1
    while True:
        r = await gh(
            "GET",
            "/user/repos",
            params={
                "affiliation": AFILIACAO,
                "per_page": 100,
                "page": pagina,
                "sort": "full_name",
            },
        )
        if r.status_code != 200:
            raise HTTPException(r.status_code, mensagem_erro(r))
        lote = r.json()
        repos.extend(resumo(x) for x in lote)
        if len(lote) < 100:
            break
        pagina += 1

    eu = usuario.json()
    return {"usuario": eu["login"], "nome": eu.get("name") or eu["login"], "repos": repos}


@app.get("/api/regras/{dono}/{nome}", dependencies=[Depends(exigir_token)])
async def checar_regras(dono: str, nome: str):
    base = caminho_repo(dono, nome)
    r = await gh("GET", base)
    if r.status_code != 200:
        raise HTTPException(r.status_code, mensagem_erro(r))
    repo = r.json()
    branch = repo["default_branch"]
    ref = quote(branch, safe="")

    perfil, protecao, rulesets, dependabot, gitignore = await asyncio.gather(
        gh("GET", f"{base}/community/profile"),
        gh("GET", f"{base}/branches/{ref}/protection"),
        gh("GET", f"{base}/rules/branches/{ref}"),
        gh("GET", f"{base}/vulnerability-alerts"),
        gh("GET", f"{base}/contents/.gitignore"),
    )

    regras = [
        regra("Descricao", "ok" if repo.get("description") else "falha",
              repo.get("description") or "repositorio sem descricao")
    ]
    if perfil.status_code == 200:
        arquivos = perfil.json().get("files", {})
        licenca = arquivos.get("license")
        regras.append(regra("README", "ok" if arquivos.get("readme") else "falha",
                            "README presente" if arquivos.get("readme") else "sem README"))
        regras.append(regra("Licenca", "ok" if licenca else "falha",
                            (licenca.get("spdx_id") or licenca.get("name") or "presente")
                            if licenca else "sem arquivo LICENSE"))
    else:
        regras.append(regra("README", "nd", mensagem_erro(perfil)))
        regras.append(regra("Licenca", "nd", mensagem_erro(perfil)))
    regras.append(por_status(".gitignore", gitignore, ".gitignore na raiz", "sem .gitignore na raiz"))
    regras.extend(regras_de_branch(branch, protecao, rulesets))
    regras.extend(regras_de_seguranca(repo))
    regras.append(por_status("Dependabot", dependabot, "alertas ativados", "alertas desativados"))

    return {"full_name": repo["full_name"], "regras": regras}


class TrocaVisibilidade(BaseModel):
    full_name: str
    privado: bool


@app.post("/api/visibilidade", dependencies=[Depends(exigir_token)])
async def trocar_visibilidade(troca: TrocaVisibilidade):
    dono, _, nome = troca.full_name.partition("/")
    r = await gh("PATCH", caminho_repo(dono, nome), json={"private": troca.privado})
    if r.status_code != 200:
        raise HTTPException(r.status_code, mensagem_erro(r))
    return resumo(r.json())


async def catalogo():
    if not hasattr(app.state, "catalogo"):
        modelos, licencas = await asyncio.gather(
            gh("GET", "/gitignore/templates"), gh("GET", "/licenses")
        )
        app.state.catalogo = {
            "gitignore": exigir(modelos, 200),
            "licencas": [{"chave": x["key"], "nome": x["name"]} for x in exigir(licencas, 200)],
        }
    return app.state.catalogo


def carregar_ruleset():
    try:
        dados = json.loads(ARQUIVO_RULESET.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(500, f"nao foi possivel ler {ARQUIVO_RULESET.name}: {e}") from e
    if not isinstance(dados, dict) or not dados.get("name") or not isinstance(dados.get("rules"), list):
        raise HTTPException(500, f"{ARQUIVO_RULESET.name} invalido: precisa de 'name' e 'rules'")
    # id, source, source_type etc. vem do export do GitHub e sao somente leitura
    campos = ("name", "target", "enforcement", "conditions", "rules", "bypass_actors")
    return {k: dados[k] for k in campos if k in dados}


@app.get("/api/modelos", dependencies=[Depends(exigir_token)])
async def listar_modelos():
    try:
        ruleset = carregar_ruleset()
        resumo_ruleset = {
            "arquivo": ARQUIVO_RULESET.name,
            "nome": ruleset["name"],
            "regras": [r.get("type", "?") for r in ruleset["rules"]],
            "bypass_admin": any(a.get("actor_type") == "RepositoryRole" and a.get("actor_id") == 5
                                for a in ruleset.get("bypass_actors", [])),
        }
    except HTTPException as e:
        resumo_ruleset = {"arquivo": ARQUIVO_RULESET.name, "erro": e.detail}
    return {**await catalogo(), "ruleset": resumo_ruleset}


async def adicionar_arquivo(base, caminho, conteudo, mensagem):
    existente = await gh("GET", f"{base}/contents/{caminho}")
    if existente.status_code == 200:
        raise HTTPException(409, f"{caminho} ja existe no repositorio")
    url = f"{base}/contents/{caminho}"
    corpo = {"message": mensagem, "content": base64.b64encode(conteudo.encode()).decode()}

    r = await gh("PUT", url, json=corpo)
    if r.status_code == 201:
        return {"mensagem": f"{caminho} commitado na branch padrao",
                "url": r.json()["commit"]["html_url"]}
    if r.status_code != 409 or "rule violation" not in r.text.lower():
        raise HTTPException(r.status_code, mensagem_erro(r))

    # branch padrao exige pull request: commita em branch separada e abre o PR
    padrao = exigir(await gh("GET", base), 200)["default_branch"]
    ponta = exigir(await gh("GET", f"{base}/git/ref/heads/{quote(padrao)}"), 200)
    branch = "git-check/" + caminho.lower().strip(".").replace(".", "-")
    exigir(await gh("POST", f"{base}/git/refs",
                    json={"ref": f"refs/heads/{branch}", "sha": ponta["object"]["sha"]}), 201)
    exigir(await gh("PUT", url, json={**corpo, "branch": branch}), 201)
    pr = exigir(await gh("POST", f"{base}/pulls",
                         json={"title": mensagem, "head": branch, "base": padrao,
                               "body": "Aberto pelo git_check."}), 201)
    return {"mensagem": f"branch padrao exige PR: aberto o #{pr['number']}", "url": pr["html_url"]}


class Acao(BaseModel):
    full_name: str

    def base(self):
        dono, _, nome = self.full_name.partition("/")
        return caminho_repo(dono, nome)


class AcaoDescricao(Acao):
    descricao: str = Field(min_length=1, max_length=350)


class AcaoGitignore(Acao):
    modelo: str


class AcaoReadme(Acao):
    conteudo: str = Field(min_length=1, max_length=100_000)


class AcaoLicenca(Acao):
    licenca: str
    titular: str = Field(min_length=1, max_length=200)


class AcaoRegras(Acao):
    ruleset: bool = False
    secret_scanning: bool = False
    push_protection: bool = False


class AcaoDependabot(Acao):
    security_updates: bool = False


@app.post("/api/acoes/descricao", dependencies=[Depends(exigir_token)])
async def acao_descricao(acao: AcaoDescricao):
    exigir(await gh("PATCH", acao.base(), json={"description": acao.descricao}), 200)
    return {"mensagem": "descricao atualizada"}


@app.post("/api/acoes/gitignore", dependencies=[Depends(exigir_token)])
async def acao_gitignore(acao: AcaoGitignore):
    base = acao.base()
    if acao.modelo not in (await catalogo())["gitignore"]:
        raise HTTPException(422, f"modelo de .gitignore desconhecido: {acao.modelo}")
    modelo = exigir(await gh("GET", f"/gitignore/templates/{quote(acao.modelo, safe='')}"), 200)
    return await adicionar_arquivo(
        base, ".gitignore", modelo["source"], f"Adiciona .gitignore ({acao.modelo})"
    )


@app.post("/api/acoes/readme", dependencies=[Depends(exigir_token)])
async def acao_readme(acao: AcaoReadme):
    return await adicionar_arquivo(acao.base(), "README.md", acao.conteudo, "Adiciona README.md")


@app.post("/api/acoes/licenca", dependencies=[Depends(exigir_token)])
async def acao_licenca(acao: AcaoLicenca):
    base = acao.base()
    if acao.licenca not in [x["chave"] for x in (await catalogo())["licencas"]]:
        raise HTTPException(422, f"licenca desconhecida: {acao.licenca}")
    licenca = exigir(await gh("GET", f"/licenses/{acao.licenca}"), 200)
    texto = (licenca["body"]
             .replace("[year]", str(date.today().year))
             .replace("[fullname]", acao.titular))
    return await adicionar_arquivo(
        base, "LICENSE", texto, f"Adiciona licenca {licenca.get('spdx_id') or acao.licenca}"
    )


@app.post("/api/acoes/regras", dependencies=[Depends(exigir_token)])
async def acao_regras(acao: AcaoRegras):
    base = acao.base()
    ruleset = carregar_ruleset() if acao.ruleset else None
    seguranca = {}
    if acao.secret_scanning:
        seguranca["secret_scanning"] = {"status": "enabled"}
    if acao.push_protection:
        seguranca["secret_scanning_push_protection"] = {"status": "enabled"}
    if not ruleset and not seguranca:
        raise HTTPException(422, "nenhuma opcao marcada")
    if exigir(await gh("GET", base), 200)["private"]:
        raise HTTPException(422, "repositorio privado nao recebe regras")

    feito, url = [], None
    if ruleset:
        criado = exigir(await gh("POST", f"{base}/rulesets", json=ruleset), 201)
        feito.append(f"ruleset {ruleset['name']} criado")
        url = criado.get("_links", {}).get("html", {}).get("href")
    if seguranca:
        exigir(await gh("PATCH", base, json={"security_and_analysis": seguranca}), 200)
        feito.append("secret scanning ativado")
    return {"mensagem": " + ".join(feito), "url": url}


@app.post("/api/acoes/dependabot", dependencies=[Depends(exigir_token)])
async def acao_dependabot(acao: AcaoDependabot):
    base = acao.base()
    exigir(await gh("PUT", f"{base}/vulnerability-alerts"), 204)
    feito = ["alertas do Dependabot ativados"]
    if acao.security_updates:
        exigir(await gh("PUT", f"{base}/automated-security-fixes"), 204)
        feito.append("security updates ativados")
    return {"mensagem": " + ".join(feito)}


@app.get("/api/execucao", response_class=PlainTextResponse)
async def execucao():
    return PlainTextResponse(ID_EXECUCAO, headers={"Cache-Control": "no-store"})


@app.get("/", response_class=HTMLResponse)
async def pagina():
    return HTMLResponse(
        PAGINA.replace("__TOKEN__", TOKEN_PAGINA).replace("__EXECUCAO__", ID_EXECUCAO),
        headers={"Cache-Control": "no-store"},
    )


PAGINA = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>git_check</title>
<style>
  :root {
    --fundo: #f6f7f9; --cartao: #fff; --borda: #dfe3e8; --texto: #1c2128; --suave: #656d76;
    --ok: #1a7f37; --ok-bg: #dafbe1; --falha: #b42318; --falha-bg: #ffe5e2;
    --nd: #6b5900; --nd-bg: #fff4c2; --acento: #0969da; --perigo: #b42318;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --fundo: #0d1117; --cartao: #161b22; --borda: #30363d; --texto: #e6edf3; --suave: #8b949e;
      --ok: #56d364; --ok-bg: #12301c; --falha: #ff8178; --falha-bg: #3d1513;
      --nd: #e3b341; --nd-bg: #33290a; --acento: #58a6ff; --perigo: #ff8178;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--fundo); color: var(--texto);
         font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .layout { display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 24px;
            max-width: 1440px; margin: 0 auto; padding: 24px 16px 64px; }
  aside { position: sticky; top: 24px; align-self: start; }
  aside h2 { font-size: 12px; color: var(--suave); text-transform: uppercase; letter-spacing: .04em; }
  aside nav { display: flex; flex-direction: column; gap: 6px; }
  aside nav button { display: flex; justify-content: space-between; align-items: center; gap: 8px;
                     text-align: left; white-space: normal; padding: 8px 10px; }
  aside p { color: var(--suave); font-size: 12px; }
  .cont { font-size: 11px; font-variant-numeric: tabular-nums; border-radius: 10px; padding: 0 7px;
          background: var(--falha-bg); color: var(--falha); font-weight: 600; }
  .cont.zero { background: var(--ok-bg); color: var(--ok); }
  @media (max-width: 800px) {
    .layout { grid-template-columns: minmax(0, 1fr); }
    aside { position: static; }
  }
  header { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 20px; }
  h1 { font-size: 20px; margin: 0; }
  h1 small { font-weight: 400; color: var(--suave); font-size: 14px; margin-left: 6px; }
  .espaco { flex: 1; }
  input[type=search], input[type=text] {
    background: var(--cartao); color: var(--texto); border: 1px solid var(--borda);
    border-radius: 6px; padding: 6px 10px; font: inherit; }
  input[type=search] { width: 220px; }
  button { font: inherit; border: 1px solid var(--borda); background: var(--cartao); color: var(--texto);
           border-radius: 6px; padding: 5px 12px; cursor: pointer; white-space: nowrap; }
  button:hover:not(:disabled) { border-color: var(--acento); color: var(--acento); }
  button:disabled { opacity: .5; cursor: not-allowed; }
  button.perigo { background: var(--perigo); border-color: var(--perigo); color: #fff; }
  button.perigo:hover:not(:disabled) { color: #fff; filter: brightness(1.1); }
  .resumo { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
  .resumo div { background: var(--cartao); border: 1px solid var(--borda); border-radius: 8px;
                padding: 10px 16px; min-width: 150px; }
  .resumo b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; }
  .resumo span { color: var(--suave); font-size: 12px; }
  section { margin-bottom: 32px; }
  h2 { font-size: 16px; margin: 0 0 8px; }
  h2 .qtd { color: var(--suave); font-weight: 400; }
  .tabela { background: var(--cartao); border: 1px solid var(--borda); border-radius: 8px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--borda); vertical-align: top; }
  th { font-size: 12px; color: var(--suave); font-weight: 600; }
  tr:last-child td { border-bottom: 0; }
  td.acao, th.acao { text-align: right; }
  td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  a { color: var(--acento); text-decoration: none; font-weight: 600; }
  a:hover { text-decoration: underline; }
  .desc { color: var(--suave); font-size: 12px; max-width: 320px; }
  .tag { font-size: 11px; border: 1px solid var(--borda); border-radius: 10px; padding: 0 6px;
         color: var(--suave); margin-left: 6px; font-weight: 400; }
  .regras { display: flex; flex-wrap: wrap; gap: 4px; }
  .regra { font-size: 12px; border-radius: 10px; padding: 1px 8px; cursor: help; white-space: nowrap; }
  .regra.ok { color: var(--ok); background: var(--ok-bg); }
  .regra.falha { color: var(--falha); background: var(--falha-bg); font-weight: 600; }
  .regra.nd { color: var(--nd); background: var(--nd-bg); }
  .vazio, .carregando { color: var(--suave); padding: 16px 12px; }
  .erro { color: var(--falha); }
  dialog { background: var(--cartao); color: var(--texto); border: 1px solid var(--borda);
           border-radius: 10px; padding: 20px; width: min(460px, calc(100vw - 32px)); }
  dialog::backdrop { background: rgba(0, 0, 0, .5); }
  dialog h3 { margin: 0 0 8px; font-size: 16px; }
  dialog ul { margin: 8px 0 12px; padding-left: 18px; color: var(--suave); }
  #dialogo input { width: 100%; margin: 6px 0 14px; }
  button.primario { background: var(--acento); border-color: var(--acento); color: #fff; }
  button.primario:hover:not(:disabled) { color: #fff; filter: brightness(1.1); }
  #dlg-acao { width: min(760px, calc(100vw - 32px)); }
  #dlg-acao select, #dlg-acao textarea {
    background: var(--cartao); color: var(--texto); border: 1px solid var(--borda);
    border-radius: 6px; padding: 5px 8px; font: inherit; max-width: 100%; }
  #dlg-acao textarea { width: 100%; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  #acao-opcoes { display: flex; flex-direction: column; gap: 8px; margin: 12px 0; }
  #acao-opcoes label.campo { display: flex; flex-direction: column; gap: 4px; }
  .marcar { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--suave); margin-bottom: 4px; }
  .alvos { border: 1px solid var(--borda); border-radius: 8px; max-height: 42vh; overflow-y: auto;
           margin-bottom: 14px; }
  .alvo { display: grid; grid-template-columns: minmax(140px, 1fr) minmax(0, 1.4fr); gap: 4px 12px;
          align-items: center; padding: 7px 10px; border-bottom: 1px solid var(--borda); }
  .alvo:last-child { border-bottom: 0; }
  .alvo label { display: flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
  .alvo input[type=text], .alvo select { width: 100%; }
  .resultado { grid-column: 1 / -1; font-size: 12px; color: var(--suave); overflow-wrap: anywhere; }
  .resultado:empty { display: none; }
  .resultado.feito { color: var(--ok); }
  .resultado.erro { color: var(--falha); }
  dialog .botoes { display: flex; justify-content: flex-end; gap: 8px; }
  dialog code { background: var(--fundo); padding: 1px 5px; border-radius: 4px; }
  #aviso { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); max-width: 90vw;
           background: var(--texto); color: var(--fundo); padding: 10px 16px; border-radius: 8px;
           display: none; }
</style>
</head>
<body>
<div class="layout">
<aside>
  <h2>Corrigir pendências</h2>
  <nav>
    <button data-acao="gitignore">Adicionar .gitignore <span class="cont zero" id="cont-gitignore">–</span></button>
    <button data-acao="descricao">Adicionar Descrição <span class="cont zero" id="cont-descricao">–</span></button>
    <button data-acao="readme">Adicionar README.md <span class="cont zero" id="cont-readme">–</span></button>
    <button data-acao="licenca">Adicionar Licença <span class="cont zero" id="cont-licenca">–</span></button>
    <button data-acao="regras">Adicionar regras ao repo público <span class="cont zero" id="cont-regras">–</span></button>
    <button data-acao="dependabot">Ativar alertas do Dependabot <span class="cont zero" id="cont-dependabot">–</span></button>
  </nav>
  <p>O número é a quantidade de repositórios públicos com a pendência.</p>
</aside>
<main>
  <header>
    <h1>git_check <small id="usuario"></small></h1>
    <span class="espaco"></span>
    <input type="search" id="filtro" placeholder="Filtrar por nome…" aria-label="Filtrar repositórios">
    <button id="recarregar">Recarregar</button>
  </header>

  <div class="resumo">
    <div><b id="n-publicos">–</b><span>públicos</span></div>
    <div><b id="n-privados">–</b><span>privados</span></div>
    <div><b id="n-pendentes">–</b><span>públicos com regra pendente</span></div>
  </div>

  <section>
    <h2>Públicos <span class="qtd" id="qtd-publicos"></span></h2>
    <div class="tabela">
      <table>
        <thead><tr><th>Repositório</th><th>Regras</th><th>Nota</th><th class="acao">Visibilidade</th></tr></thead>
        <tbody id="publicos"><tr><td colspan="4" class="carregando">Carregando…</td></tr></tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Privados <span class="qtd" id="qtd-privados"></span></h2>
    <div class="tabela">
      <table>
        <thead><tr><th>Repositório</th><th>Linguagem</th><th>Último push</th><th class="acao">Visibilidade</th></tr></thead>
        <tbody id="privados"><tr><td colspan="4" class="carregando">Carregando…</td></tr></tbody>
      </table>
    </div>
  </section>
</main>
</div>

<dialog id="dlg-acao">
  <h3 id="acao-titulo"></h3>
  <div class="desc" id="acao-ajuda" style="max-width:none"></div>
  <div id="acao-opcoes"></div>
  <label class="marcar"><input type="checkbox" id="acao-todos"> Marcar todos</label>
  <div class="alvos" id="acao-alvos"></div>
  <div class="botoes">
    <button id="acao-fechar">Fechar</button>
    <button id="acao-aplicar" class="primario">Aplicar nos marcados</button>
  </div>
</dialog>

<dialog id="dialogo">
  <form method="dialog">
    <h3 id="dlg-titulo"></h3>
    <ul id="dlg-avisos"></ul>
    <label>Digite <code id="dlg-nome"></code> para confirmar:
      <input type="text" id="dlg-entrada" autocomplete="off" spellcheck="false">
    </label>
    <div class="botoes">
      <button value="cancelar">Cancelar</button>
      <button value="confirmar" id="dlg-confirmar" class="perigo" disabled>Confirmar</button>
    </div>
  </form>
</dialog>
<div id="aviso" role="status"></div>

<script>
const TOKEN = "__TOKEN__";
const EXECUCAO = "__EXECUCAO__";
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const SIMBOLO = {ok: "✓", falha: "✗", nd: "?"};
const AVISOS = {
  publico: ["Código, histórico de commits, issues e PRs ficam visíveis para qualquer pessoa.",
            "Segredos já commitados no histórico passam a estar expostos.",
            "Qualquer pessoa poderá fazer fork do repositório."],
  privado: ["Stars e watchers do repositório são perdidos.",
            "Forks públicos existentes são desvinculados e continuam públicos.",
            "GitHub Pages publicado pode sair do ar, dependendo do plano."],
};

let repos = [];
let regras = {};
let geracao = 0;
let catalogo = {gitignore: [], licencas: [], ruleset: null};
const NOME_REGRA = {deletion: "bloquear exclusão", non_fast_forward: "bloquear force push",
  pull_request: "exigir pull request", required_status_checks: "exigir status checks",
  required_linear_history: "histórico linear", required_signatures: "commits assinados",
  creation: "bloquear criação", update: "bloquear atualização"};
let titular = "";
let acaoAtual = null;

const MODELO_POR_LINGUAGEM = {Python: "Python", JavaScript: "Node", TypeScript: "Node", Java: "Java",
  Kotlin: "Java", Go: "Go", HCL: "Terraform", Ruby: "Ruby", Rust: "Rust", C: "C", "C++": "C++",
  Swift: "Swift", Dart: "Dart"};
const marcado = id => $(id).checked;
const caixa = (id, texto, ligada = true, desligada = false) =>
  `<label><input type="checkbox" id="${id}"${ligada && !desligada ? " checked" : ""}${desligada ? " disabled" : ""}> ${texto}</label>`;

function textoRuleset() {
  const r = catalogo.ruleset;
  if (!r) return "Arquivo do ruleset ainda não carregado.";
  if (r.erro) return `<span class="erro">${esc(r.erro)}</span>`;
  return `Criar o ruleset <b>${esc(r.nome)}</b> definido em <code>${esc(r.arquivo)}</code>: ` +
    esc(r.regras.map(t => NOME_REGRA[t] || t).join(", ")) +
    (r.bypass_admin ? " (admin do repositório pode ignorar)" : "");
}

const ACOES = {
  gitignore: {
    titulo: "Adicionar .gitignore",
    ajuda: "Commita um .gitignore (modelos do GitHub) na raiz da branch padrão. O modelo vem sugerido pela linguagem do repositório; confira antes de aplicar.",
    regras: [".gitignore"],
    controle: r => '<select><option value="">— escolha o modelo —</option>' + catalogo.gitignore.map(m =>
      `<option${m === MODELO_POR_LINGUAGEM[r.linguagem] ? " selected" : ""}>${esc(m)}</option>`).join("") + "</select>",
    corpo: (r, linha) => {
      const modelo = linha.querySelector("select").value;
      return modelo ? {modelo} : null;
    },
  },
  descricao: {
    titulo: "Adicionar Descrição",
    ajuda: "Digite a descrição de cada repositório (até 350 caracteres). Ao digitar, a linha é marcada.",
    regras: ["Descricao"],
    controle: () => '<input type="text" maxlength="350" placeholder="Descrição do repositório">',
    corpo: (r, linha) => {
      const descricao = linha.querySelector("input[type=text]").value.trim();
      return descricao ? {descricao} : null;
    },
  },
  readme: {
    titulo: "Adicionar README.md",
    ajuda: "Commita um README.md inicial na raiz da branch padrão, a partir do modelo abaixo.",
    regras: ["README"],
    opcoes: () => '<label class="campo">Modelo — <code>{nome}</code> e <code>{descricao}</code> são trocados pelos dados de cada repositório' +
      `<textarea id="op-readme" rows="6"># {nome}\n\n{descricao}\n</textarea></label>`,
    corpo: r => {
      const conteudo = $("op-readme").value.replaceAll("{nome}", r.nome).replaceAll("{descricao}", r.descricao).trim();
      return conteudo ? {conteudo: conteudo + "\n"} : null;
    },
  },
  licenca: {
    titulo: "Adicionar Licença",
    ajuda: "Commita um arquivo LICENSE na raiz da branch padrão, com o ano atual e o titular informado.",
    regras: ["Licenca"],
    opcoes: () => '<label class="campo">Licença<select id="op-licenca">' + catalogo.licencas.map(l =>
      `<option value="${esc(l.chave)}"${l.chave === "mit" ? " selected" : ""}>${esc(l.nome)}</option>`).join("") +
      `</select></label><label class="campo">Titular do copyright<input type="text" id="op-titular" value="${esc(titular)}"></label>`,
    corpo: () => {
      const nome = $("op-titular").value.trim();
      return nome && $("op-licenca").value ? {licenca: $("op-licenca").value, titular: nome} : null;
    },
  },
  regras: {
    titulo: "Adicionar regras ao repo público",
    ajuda: "Aplica na branch padrão o ruleset do arquivo JSON e ativa o secret scanning. Só repositórios públicos; em cada um é aplicado só o que está pendente nele (quem já tem ruleset não ganha outro).",
    regras: ["Branch protegida", "Sem force push", "Secret scanning", "Push protection"],
    opcoes: () =>
      caixa("op-ruleset", textoRuleset(), true, !catalogo.ruleset || !!catalogo.ruleset.erro) +
      caixa("op-secret", "Ativar secret scanning") +
      caixa("op-push", "Ativar push protection (bloqueia push com segredo)"),
    corpo: r => {
      const falta = nome => regras[r.full_name]?.regras?.some(x => x.nome === nome && x.estado === "falha");
      const branch = falta("Branch protegida") || falta("Sem force push");
      const corpo = {
        ruleset: branch && marcado("op-ruleset"),
        secret_scanning: falta("Secret scanning") && marcado("op-secret"),
        push_protection: falta("Push protection") && marcado("op-push")};
      const algo = ["ruleset", "secret_scanning", "push_protection"];
      return algo.some(k => corpo[k]) ? corpo : null;
    },
  },
  dependabot: {
    titulo: "Ativar alertas do Dependabot",
    ajuda: "Liga os alertas de vulnerabilidade em dependências (aba Security do repositório). Não altera o código; pode ser desligado depois em Settings → Advanced Security.",
    regras: ["Dependabot"],
    opcoes: () => caixa("op-secupd",
      "Ativar também os security updates (o Dependabot passa a abrir PRs corrigindo dependências vulneráveis)", false),
    corpo: () => ({security_updates: marcado("op-secupd")}),
  },
};

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, {...opcoes,
    headers: {"X-Painel-Token": TOKEN, "Content-Type": "application/json", ...(opcoes.headers || {})}});
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = corpo.detail;
    throw new Error(typeof d === "string" ? d : d ? JSON.stringify(d) : "HTTP " + r.status);
  }
  return corpo;
}

function avisar(texto) {
  const el = $("aviso");
  el.textContent = texto;
  el.style.display = "block";
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => el.style.display = "none", 6000);
}

function celulaRepo(r) {
  return `<td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.full_name)}</a>` +
    (r.fork ? '<span class="tag">fork</span>' : "") +
    (r.arquivado ? '<span class="tag">arquivado</span>' : "") +
    (r.descricao ? `<div class="desc">${esc(r.descricao)}</div>` : "") + "</td>";
}

function celulaAcao(r) {
  const destino = r.privado ? "público" : "privado";
  const bloqueio = !r.admin ? "sem permissão de admin neste repositório"
    : r.fork ? "forks não podem mudar de visibilidade"
    : r.arquivado ? "desarquive o repositório antes de mudar a visibilidade" : "";
  return `<td class="acao"><button data-repo="${esc(r.full_name)}"` +
    (bloqueio ? ` disabled title="${esc(bloqueio)}"` : "") + `>Tornar ${destino}</button></td>`;
}

function celulasRegras(r) {
  const c = regras[r.full_name];
  if (!c) return '<td class="carregando">checando…</td><td class="num">–</td>';
  if (c.erro) return `<td class="erro">${esc(c.erro)}</td><td class="num">–</td>`;
  const ok = c.regras.filter(x => x.estado === "ok").length;
  const pills = c.regras.map(x =>
    `<span class="regra ${x.estado}" title="${esc(x.detalhe)}">${SIMBOLO[x.estado]} ${esc(x.nome)}</span>`).join("");
  return `<td><div class="regras">${pills}</div></td><td class="num">${ok}/${c.regras.length}</td>`;
}

function desenhar() {
  const termo = $("filtro").value.trim().toLowerCase();
  const visiveis = repos.filter(r => r.full_name.toLowerCase().includes(termo));
  const publicos = visiveis.filter(r => !r.privado);
  const privados = visiveis.filter(r => r.privado);
  const vazio = '<tr><td colspan="4" class="vazio">Nenhum repositório.</td></tr>';

  $("publicos").innerHTML = publicos.map(r =>
    `<tr>${celulaRepo(r)}${celulasRegras(r)}${celulaAcao(r)}</tr>`).join("") || vazio;
  $("privados").innerHTML = privados.map(r =>
    `<tr>${celulaRepo(r)}<td>${esc(r.linguagem) || "–"}</td><td class="num">` +
    (r.ultimo_push ? new Date(r.ultimo_push).toLocaleDateString("pt-BR") : "–") +
    `</td>${celulaAcao(r)}</tr>`).join("") || vazio;

  const todosPublicos = repos.filter(r => !r.privado);
  $("n-publicos").textContent = todosPublicos.length;
  $("n-privados").textContent = repos.length - todosPublicos.length;
  $("n-pendentes").textContent = todosPublicos.filter(r =>
    regras[r.full_name]?.regras?.some(x => x.estado === "falha")).length;
  $("qtd-publicos").textContent = termo ? `(${publicos.length} no filtro)` : "";
  $("qtd-privados").textContent = termo ? `(${privados.length} no filtro)` : "";
  for (const chave in ACOES) {
    const n = pendentes(chave).length;
    $("cont-" + chave).textContent = n;
    $("cont-" + chave).classList.toggle("zero", n === 0);
  }
}

async function checar(full_name, g = geracao) {
  let resultado;
  try {
    resultado = await api("/api/regras/" + full_name);
  } catch (e) {
    resultado = {erro: e.message};
  }
  if (g !== geracao) return;
  regras[full_name] = resultado;
  desenhar();
}

async function checarTodos(g) {
  const fila = repos.filter(r => !r.privado).map(r => r.full_name);
  const trabalhador = async () => {
    while (fila.length && g === geracao) await checar(fila.shift(), g);
  };
  await Promise.all(Array.from({length: 6}, trabalhador));
}

async function carregar() {
  const g = ++geracao;
  $("recarregar").disabled = true;
  try {
    const dados = await api("/api/repos");
    repos = dados.repos;
    regras = {};
    $("usuario").textContent = "@" + dados.usuario;
    titular = dados.nome;
    api("/api/modelos").then(c => catalogo = c).catch(e => avisar("Erro ao carregar modelos: " + e.message));
    desenhar();
    await checarTodos(g);
  } catch (e) {
    avisar("Erro ao listar repositórios: " + e.message);
  } finally {
    $("recarregar").disabled = false;
  }
}

function confirmar(repo) {
  const destino = repo.privado ? "publico" : "privado";
  $("dlg-titulo").textContent = `Tornar ${repo.full_name} ${repo.privado ? "público" : "privado"}?`;
  $("dlg-avisos").innerHTML = AVISOS[destino].map(a => `<li>${esc(a)}</li>`).join("");
  $("dlg-nome").textContent = repo.nome;
  $("dlg-entrada").value = "";
  $("dlg-confirmar").disabled = true;
  $("dlg-entrada").oninput = e => $("dlg-confirmar").disabled = e.target.value !== repo.nome;
  const dlg = $("dialogo");
  return new Promise(resolver => {
    dlg.onclose = () => resolver(dlg.returnValue === "confirmar" && $("dlg-entrada").value === repo.nome);
    dlg.returnValue = "";
    dlg.showModal();
    $("dlg-entrada").focus();
  });
}

async function trocar(botao) {
  const repo = repos.find(r => r.full_name === botao.dataset.repo);
  if (!repo || !(await confirmar(repo))) return;
  botao.disabled = true;
  botao.textContent = "Alterando…";
  try {
    const novo = await api("/api/visibilidade", {method: "POST",
      body: JSON.stringify({full_name: repo.full_name, privado: !repo.privado})});
    repos[repos.indexOf(repo)] = novo;
    delete regras[repo.full_name];
    avisar(`${novo.full_name} agora é ${novo.privado ? "privado" : "público"}.`);
    desenhar();
    if (!novo.privado) checar(novo.full_name);
  } catch (e) {
    avisar(`Não foi possível alterar ${repo.full_name}: ${e.message}`);
    desenhar();
  }
}

function pendentes(chave) {
  return repos.filter(r => !r.privado && !r.arquivado && r.admin &&
    regras[r.full_name]?.regras?.some(x => x.estado === "falha" && ACOES[chave].regras.includes(x.nome)));
}

function abrirAcao(chave) {
  const acao = ACOES[chave];
  const alvos = pendentes(chave);
  acaoAtual = chave;
  $("acao-titulo").textContent = acao.titulo;
  $("acao-ajuda").textContent = acao.ajuda;
  $("acao-opcoes").innerHTML = acao.opcoes ? acao.opcoes() : "";
  $("acao-alvos").innerHTML = alvos.map(r =>
    `<div class="alvo" data-repo="${esc(r.full_name)}"><label><input type="checkbox"> ${esc(r.nome)}</label>` +
    (acao.controle ? acao.controle(r) : "<span></span>") + '<span class="resultado"></span></div>').join("") ||
    '<div class="vazio">Nenhum repositório público com esta pendência.</div>';
  $("acao-todos").checked = false;
  $("acao-aplicar").disabled = !alvos.length;
  $("dlg-acao").showModal();
}

async function aplicarAcao() {
  const acao = ACOES[acaoAtual];
  const chave = acaoAtual;
  const linhas = [...$("acao-alvos").querySelectorAll(".alvo")]
    .filter(l => l.querySelector("input[type=checkbox]").checked);
  if (!linhas.length) return avisar("Marque ao menos um repositório.");
  $("acao-aplicar").disabled = true;
  for (const linha of linhas) {
    const repo = repos.find(r => r.full_name === linha.dataset.repo);
    const saida = linha.querySelector(".resultado");
    const corpo = repo && acao.corpo(repo, linha);
    if (!corpo) {
      saida.className = "resultado erro";
      saida.textContent = "✗ nada a aplicar nesta linha (campo vazio ou opções desmarcadas)";
      continue;
    }
    saida.className = "resultado";
    saida.textContent = "aplicando…";
    try {
      const res = await api("/api/acoes/" + chave,
        {method: "POST", body: JSON.stringify({full_name: repo.full_name, ...corpo})});
      saida.className = "resultado feito";
      saida.innerHTML = "✓ " + (res.url
        ? `<a href="${esc(res.url)}" target="_blank" rel="noopener">${esc(res.mensagem)}</a>` : esc(res.mensagem));
      const marca = linha.querySelector("input[type=checkbox]");
      marca.checked = false;
      marca.disabled = true;
      if (corpo.descricao) repo.descricao = corpo.descricao;
      checar(repo.full_name);
    } catch (e) {
      saida.className = "resultado erro";
      saida.textContent = "✗ " + e.message;
    }
  }
  $("acao-aplicar").disabled = false;
}

document.addEventListener("click", e => {
  const botao = e.target.closest("button[data-repo]");
  if (botao) return trocar(botao);
  const acao = e.target.closest("button[data-acao]");
  if (acao) abrirAcao(acao.dataset.acao);
});
$("acao-fechar").addEventListener("click", () => $("dlg-acao").close());
$("acao-aplicar").addEventListener("click", aplicarAcao);
$("acao-todos").addEventListener("change", e => {
  for (const c of $("acao-alvos").querySelectorAll("input[type=checkbox]:not(:disabled)")) c.checked = e.target.checked;
});
$("acao-alvos").addEventListener("input", e => {
  if (e.target.matches("input[type=text]"))
    e.target.closest(".alvo").querySelector("input[type=checkbox]").checked = e.target.value.trim() !== "";
});
$("dlg-entrada").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); if (!$("dlg-confirmar").disabled) $("dlg-confirmar").click(); }
});
$("filtro").addEventListener("input", desenhar);
$("recarregar").addEventListener("click", carregar);
carregar();

// auto-atualizacao: o servidor reinicia quando o codigo muda e ganha outro ID_EXECUCAO
// (com erro de sintaxe o servidor nao responde; o timeout evita acumular requisicoes)
(async function vigiar() {
  try {
    const r = await fetch("/api/execucao", {cache: "no-store", signal: AbortSignal.timeout(2000)});
    if (r.ok && (await r.text()) !== EXECUCAO) return location.reload();
  } catch (e) {}
  setTimeout(vigiar, 1000);
})();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Painel web local para checar repositorios do GitHub.")
    parser.add_argument("--porta", type=int, default=PORTA, help=f"porta local (padrao {PORTA})")
    parser.add_argument("--sem-navegador", action="store_true", help="nao abre o navegador automaticamente")
    parser.add_argument("--sem-recarga", action="store_true",
                        help="nao reinicia o servidor quando o codigo muda")
    args = parser.parse_args()

    try:
        obter_token()
    except RuntimeError as e:
        sys.exit(f"Erro: {e}")

    url = f"http://{HOST}:{args.porta}"
    recarga = "" if args.sem_recarga else ", auto-recarga ativa"
    print(f"git_check em {url} (Ctrl+C para sair{recarga})")
    if not args.sem_navegador:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    if args.sem_recarga:
        uvicorn.run(app, host=HOST, port=args.porta, log_level="warning")
        return

    pasta = Path(__file__).resolve().parent
    uvicorn.run(
        f"{Path(__file__).stem}:app",
        app_dir=str(pasta),
        host=HOST,
        port=args.porta,
        log_level="warning",
        reload=True,
        reload_dirs=[str(pasta)],
    )


if __name__ == "__main__":
    main()

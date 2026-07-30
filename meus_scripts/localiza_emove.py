#!/usr/bin/env python3

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

MAPA_EXTENSOES = {
    ".doc":  "DOCS",
    ".docx": "DOCS",
    ".xls":  "XLS",
    ".xlsx": "XLS",
    ".pdf":  "PDFs",
}

SUBPASTAS = ["DOCS", "XLS", "PDFs"]


def parse_args():
    p = argparse.ArgumentParser(
        description="Localiza PDF/DOC/DOCX/XLS/XLSX e move para Documentos, "
                    "detectando repetidos."
    )
    p.add_argument("origem", nargs="?", default=None,
                   help="Pasta a ser varrida (recursivamente). "
                        "Se omitida, o script pergunta.")
    p.add_argument("--documentos",
                   default=str(Path.home() / "Documentos"),
                   help="Pasta 'Documentos' de destino (padrao: ~/Documents).")
    p.add_argument("--dry-run", action="store_true",
                   help="So mostra o que faria, sem mover/remover nada.")
    p.add_argument("--acao", choices=["tudo", "mover", "limpar"], default=None,
                   help="tudo=mover e limpar pastas vazias (padrao); "
                        "mover=so mover arquivos; limpar=so remover pastas "
                        "vazias. Se omitido, um menu interativo pergunta.")
    return p.parse_args()


def menu_acao():
    print("O que voce quer fazer?")
    print("  1) Localizar e mover arquivos + remover pastas vazias")
    print("  2) So localizar e mover arquivos")
    print("  3) So remover pastas vazias na origem")
    opcoes = {"1": "tudo", "2": "mover", "3": "limpar"}
    while True:
        try:
            escolha = input("Escolha [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(1)
        if escolha in opcoes:
            return opcoes[escolha]
        print("Opcao invalida.")


def hash_arquivo(caminho, bloco=1024 * 1024):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(bloco), b""):
            h.update(pedaco)
    return h.hexdigest()


def destino_sem_conflito(pasta_destino, nome_arquivo, hash_origem):
    destino = pasta_destino / nome_arquivo
    if not destino.exists():
        return ("mover", destino)

    if destino.is_file() and hash_arquivo(destino) == hash_origem:
        return ("pular", destino)

    base = destino.stem
    ext = destino.suffix
    i = 1
    while True:
        candidato = pasta_destino / f"{base}_{i}{ext}"
        if not candidato.exists():
            return ("mover", candidato)
        if candidato.is_file() and hash_arquivo(candidato) == hash_origem:
            return ("pular", candidato)
        i += 1


def remove_pastas_vazias(origem, pastas_protegidas, dry_run):
    protegidas = {p.lower() for p in pastas_protegidas}
    removidas = 0
    pastas = sorted(
        (p for p in origem.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for pasta in pastas:
        if str(pasta.resolve()).lower() in protegidas:
            continue
        try:
            if any(pasta.iterdir()):
                continue
        except OSError:
            continue
        if dry_run:
            print(f"[remover pasta vazia] {pasta}")
            removidas += 1
        else:
            try:
                pasta.rmdir()
                print(f"[removida] {pasta}")
                removidas += 1
            except OSError as e:
                print(f"[ERRO] falha ao remover {pasta}: {e}")
    return removidas


def mover_arquivos(origem, destinos, pastas_destino_resolvidas, dry_run):
    for caminho in destinos.values():
        if dry_run:
            if not caminho.exists():
                print(f"[criar] {caminho}")
        else:
            caminho.mkdir(parents=True, exist_ok=True)

    alvos = []
    for arquivo in origem.rglob("*"):
        if not arquivo.is_file():
            continue
        if arquivo.suffix.lower() not in MAPA_EXTENSOES:
            continue
        pais_arquivo = {str(p).lower() for p in arquivo.resolve().parents}
        if any(dest in pais_arquivo for dest in pastas_destino_resolvidas):
            continue
        alvos.append(arquivo)

    print(f"Arquivos-alvo encontrados: {len(alvos)}")
    print("-" * 60)

    vistos = {}
    movidos = 0
    pulados_destino = 0
    duplicatas_origem = 0
    erros = 0

    for arquivo in sorted(alvos):
        try:
            h = hash_arquivo(arquivo)
        except Exception as e:
            print(f"[ERRO] nao consegui ler {arquivo}: {e}")
            erros += 1
            continue

        if h in vistos:
            print(f"[REPETIDO] {arquivo}")
            print(f"           identico a: {vistos[h]}  (mantido no lugar)")
            duplicatas_origem += 1
            continue
        vistos[h] = arquivo

        subpasta = MAPA_EXTENSOES[arquivo.suffix.lower()]
        pasta_destino = destinos[subpasta]

        if dry_run and not pasta_destino.exists():
            print(f"[mover] {arquivo.name}  ->  {pasta_destino}/")
            movidos += 1
            continue

        acao, destino = destino_sem_conflito(pasta_destino, arquivo.name, h)

        if acao == "pular":
            print(f"[JA EXISTE] {arquivo.name} identico ja esta em {pasta_destino.name}/ "
                  f"-> mantido na origem")
            pulados_destino += 1
            continue

        if dry_run:
            print(f"[mover] {arquivo.name}  ->  {destino}")
            movidos += 1
            continue

        try:
            shutil.move(str(arquivo), str(destino))
            print(f"[movido] {arquivo.name}  ->  {subpasta}/{destino.name}")
            movidos += 1
        except Exception as e:
            print(f"[ERRO] falha ao mover {arquivo}: {e}")
            erros += 1

    return {
        "alvos": len(alvos),
        "movidos": movidos,
        "duplicatas_origem": duplicatas_origem,
        "pulados_destino": pulados_destino,
        "erros": erros,
    }


def main():
    args = parse_args()

    caminho_origem = args.origem
    if not caminho_origem:
        try:
            caminho_origem = input("Digite o caminho da pasta a ser analisada: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(1)
        caminho_origem = caminho_origem.strip().strip('"').strip("'")

    if not caminho_origem:
        print("Nenhum caminho informado. Cancelado.")
        sys.exit(1)

    origem = Path(caminho_origem).expanduser().resolve()
    documentos = Path(args.documentos).expanduser().resolve()

    if not origem.is_dir():
        print(f"ERRO: pasta de origem nao encontrada: {origem}")
        sys.exit(1)

    acao = args.acao or menu_acao()

    destinos = {nome: documentos / nome for nome in SUBPASTAS}
    pastas_destino_resolvidas = [str(d.resolve()).lower() for d in destinos.values()]

    print(f"Origem     : {origem}")
    if acao != "limpar":
        print(f"Documentos : {documentos}")
    if args.dry_run:
        print("Modo       : DRY-RUN (nada sera movido/removido)")
    print("-" * 60)

    stats = None
    if acao in ("tudo", "mover"):
        stats = mover_arquivos(origem, destinos, pastas_destino_resolvidas, args.dry_run)

    pastas_removidas = None
    if acao in ("tudo", "limpar"):
        print("-" * 60)
        pastas_removidas = remove_pastas_vazias(
            origem, pastas_destino_resolvidas, args.dry_run
        )

    print("-" * 60)
    print("RESUMO")
    if stats is not None:
        print(f"  Arquivos-alvo encontrados     : {stats['alvos']}")
        print(f"  Movidos {'(simulado)' if args.dry_run else '           '}          : {stats['movidos']}")
        print(f"  Repetidos na origem (mantidos): {stats['duplicatas_origem']}")
        print(f"  Ja existiam no destino        : {stats['pulados_destino']}")
        print(f"  Erros                         : {stats['erros']}")
    if pastas_removidas is not None:
        print(f"  Pastas vazias removidas       : {pastas_removidas}")
    if args.dry_run:
        print("\n(dry-run: nada foi movido nem removido de fato)")


if __name__ == "__main__":
    main()

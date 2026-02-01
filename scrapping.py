from bs4 import BeautifulSoup, Tag
import requests
from typing import List
from db import obter_ufs_usuario, adicionar_concurso, usuario_ja_recebeu, obter_id_concurso, marcar_concurso_enviado

def concursos_rj() -> List[Tag]:
    link = "https://www.pciconcursos.com.br/concursos/#RJ"

    html = requests.get(link)
    soup = BeautifulSoup(html.text, 'html.parser')
    concursos = soup.select(".na, .ea, .da")

    return [
        c for c in concursos
        if c.select_one(".cc").text.strip() == "RJ"
    ]

def concursos_por_uf(uf: str) -> List[Tag]:
    link = "https://www.pciconcursos.com.br/concursos/"

    html = requests.get(link, timeout=10)
    soup = BeautifulSoup(html.text, "html.parser")

    concursos = soup.select(".na, .ea, .da")

    return [
        c for c in concursos
        if c.select_one(".cc") and c.select_one(".cc").text.strip().upper() == uf.upper()
    ]



def extrair_dados_concurso(c):
    detalhes = c.select_one(".cd")

    titulo = c.select_one(".ca a").get("title")
    link = c.select_one(".ca a").get("href")
    nome = titulo.split("-")[0].strip()

    data = c.select_one(".ce").get_text(" | ", strip=True)

    vagas = detalhes.contents[0].strip()
    cargos = detalhes.select_one("span").contents[0].strip()
    escolaridade = detalhes.select_one("span span").text.strip()

    uf = c.select_one(".cc").text.strip()

    mensagem = (
        f"📌 {nome}\n"
        f"📍 Estado: {uf}\n"
        f"📅 Data limite: {data}\n"
        f"💰 Remuneração: {vagas}\n"
        f"🧑‍💼 Cargo: {cargos}\n"
        f"🎓 Escolaridade: {escolaridade}\n\n"
        f"🔗 Mais detalhes: {link}\n"
    )

    return {
        "titulo": titulo,
        "link": link,
        "data": data,
        "estado": uf,
        "vagas": vagas,
        "cargos": cargos,
        "escolaridade": escolaridade,
        "mensagem": mensagem
    }




def mensagens_novas_para_usuario(user_id: int) -> list[str]:
    mensagens = []
    ufs = obter_ufs_usuario(user_id)

    for uf in ufs:
        for c in concursos_por_uf(uf):
            dados = extrair_dados_concurso(c)

            adicionar_concurso(
                dados["titulo"],
                dados["link"],
                dados["data"],
                dados["vagas"],
                dados["cargos"],
                dados["escolaridade"],
                dados["estado"]
            )

            concurso_id = obter_id_concurso(dados["titulo"])

            if not usuario_ja_recebeu(user_id, concurso_id):
                mensagens.append(dados["mensagem"])
                marcar_concurso_enviado(user_id, concurso_id)

    return mensagens


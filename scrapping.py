from bs4 import BeautifulSoup, Tag
import requests
from typing import List
from db import adicionar_concurso

def concursos_rj() -> List[Tag]:
    link = "https://www.pciconcursos.com.br/concursos/#RJ"

    html = requests.get(link)
    soup = BeautifulSoup(html.text, 'html.parser')
    #print(soup)

    concursos = soup.select(".na, .ea, .da")

    concursos_rj = []
    for concurso in concursos:
        estado = concurso.select_one(".cc")
        if estado.text.strip() == 'RJ':
            concursos_rj.append(concurso)
    
    return concursos_rj


def mensagens_todos() -> List[str]:
    msg = []
    for c in concursos_rj():
        detalhes = c.select_one(".cd")

        titulo  = c.select_one(".ca a").get("title")
        link =  c.select_one(".ca a").get("href")
        nome = titulo.split("-")[0]
        data = c.select_one(".ce").get_text(" | ", strip=True)
        vagas  = detalhes.contents[0].strip()
        cargos = detalhes.select_one("span").contents[0].strip()
        escolaridade = detalhes.select_one("span span").text.strip()


        text = f"\n{nome}\nData limite: {data}\nRemuneração: {vagas}\nCargo: {cargos}\nEscolaridade: {escolaridade}\n\nMais detalhes: {link}\n"
        #print(text)
        #print("#######################################")
        msg.append(text)

    return msg


def mensagens_novos() -> List[str]:
    msg = []
    for c in concursos_rj():
        detalhes = c.select_one(".cd")

        titulo  = c.select_one(".ca a").get("title")
        link =  c.select_one(".ca a").get("href")
        nome = titulo.split("-")[0]
        data = c.select_one(".ce").get_text(" | ", strip=True)
        vagas  = detalhes.contents[0].strip()
        cargos = detalhes.select_one("span").contents[0].strip()
        escolaridade = detalhes.select_one("span span").text.strip()

        if adicionar_concurso(titulo, link, data):
            text = f"\n{nome}\nData limite: {data}\nRemuneração: {vagas}\nCargo: {cargos}\nEscolaridade: {escolaridade}\n\nMais detalhes: {link}\n"
            #print(text)
            #print("#######################################")
            msg.append(text)

    return msg  
from bs4 import BeautifulSoup
import requests

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


print(len(concursos_rj))

for c in concursos_rj:
    detalhes = c.select_one(".cd")

    titulo  = c.select_one(".ca a").get("title")
    link =  c.select_one(".ca a").get("href")
    nome = titulo.split("-")[0]
    data = c.select_one(".ce").get_text(" | ", strip=True)
    vagas  = detalhes.contents[0].strip()
    cargos = detalhes.select_one("span").contents[0].strip()
    escolaridade = detalhes.select_one("span span").text.strip()

    text = f"{nome}\nData limite: {data}\nRemuneração: {vagas}\nCargo: {cargos}\nEscolaridade: {escolaridade}\n\nMais detalhes: {link}"
    print(text)

    print("#######################################")
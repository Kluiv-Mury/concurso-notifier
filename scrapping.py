import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from datetime import datetime

def concursos_ache_conc(estado: str) -> List[Dict[str, str]]:
    estado_formatado = estado.replace(" ", "-").strip().lower()
    link = f"https://www.acheconcursos.com.br/concursos-{estado_formatado}"
    html = requests.get(link)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(link, headers=headers)
    if response.status_code != 200:
        print(f"Erro na requisição: {response.status_code} para {link}")
        return []

    soup = BeautifulSoup(html.text, "html.parser")
    concursos = []

    for row in soup.select("table.tbl-conc tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue  

        link_tag = cols[0].find("a")
        titulo_tag = cols[0].find("span", class_="titulo")
        nivel_tag = cols[0].find("span", class_="vagas")

        titulo = titulo_tag.get_text(strip=True) if titulo_tag else ""
        link = link_tag["href"] if link_tag else ""
        nivel = nivel_tag.get_text(strip=True).replace("Nível:", "").strip() if nivel_tag else None
        inscricoes_ate = cols[1].get_text(strip=True)
        vagas = cols[2].get_text(strip=True)
        salario_max = cols[3].get_text(strip=True)

        cargos = "Não informado"  
        escolaridade = "Não especificado"  

        concursos.append({
            "titulo": titulo,
            "link": link,
            "nivel": nivel,
            "inscricoes_ate": inscricoes_ate,
            "vagas": vagas,
            "salario_max": salario_max,
            "cargos": cargos,
            "escolaridade": escolaridade
        })

    print(f"Concursos encontrados para {estado_formatado}: {len(concursos)} concursos.")
    return concursos

import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import time
import random

session = requests.Session()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/"
}


def concursos_ache_conc(estado: str) -> List[Dict[str, str]]:
    estado_formatado = estado.replace(" ", "-").strip().lower()
    link = f"https://www.acheconcursos.com.br/concursos-{estado_formatado}"

    for tentativa in range(3):
        try:
            response = session.get(link, headers=HEADERS, timeout=15)

            if response.status_code == 200:
                break

            if response.status_code == 429:
                sleep = random.uniform(6, 12)
                print(f"[429] Bloqueio temporário → aguardando {sleep:.1f}s ({estado_formatado})")
                time.sleep(sleep)
            else:
                print(f"Erro HTTP {response.status_code} → {link}")
                return []

        except requests.exceptions.RequestException as e:
            sleep = random.uniform(4, 10)
            print(f"Erro conexão → retry em {sleep:.1f}s: {e}")
            time.sleep(sleep)
    else:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
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

        concursos.append({
            "titulo": titulo,
            "link": link,
            "nivel": nivel,
            "inscricoes_ate": inscricoes_ate,
            "vagas": vagas,
            "salario_max": salario_max
        })

    time.sleep(random.uniform(1.5, 3.5))  

    print(f"Concursos encontrados para {estado_formatado}: {len(concursos)} concursos.")
    return concursos

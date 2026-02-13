from telegram.ext import ContextTypes
from config import logger, SIGLAS_ESTADOS
from db import (
    adicionar_concurso, listar_usuarios, obter_ufs_usuario, 
    obter_filtros, buscar_concursos_filtrados, concurso_ja_enviado, 
    adicionar_concurso_enviado
)
from scrapping import concursos_ache_conc

async def atualizar_base_concursos(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Iniciando scraping global...")
    for uf in SIGLAS_ESTADOS.values():
        logger.info(f"Scraping concursos da UF: {uf}")
        concursos = concursos_ache_conc(uf)
        if not concursos:continue

        for c in concursos:
            adicionar_concurso(c['titulo'], c['link'], c['inscricoes_ate'], c['vagas'], c['salario_max'], c['nivel'], uf)
    logger.info("Fim do scraping global.")

async def buscar_e_enviar_concursos(context: ContextTypes.DEFAULT_TYPE):
    usuarios = await listar_usuarios()
    logger.info(f"Enviando alertas para {len(usuarios)} usuários.")

    for user_id in usuarios:
        ufs = obter_ufs_usuario(user_id)
        if not ufs: continue

        salario, nivel, vagas = obter_filtros(user_id)
        concursos = buscar_concursos_filtrados(ufs, salario, nivel, vagas)
        
        for c in concursos:
            if concurso_ja_enviado(user_id, c['id']): continue
            adicionar_concurso_enviado(user_id, c['id'])
            
            msg = f"🔔 <b>{c['titulo']}</b>\n💵 {c['salario_max']} | 🏢 {c['vagas']} vagas\n📅 Até: {c['inscricoes_ate']}\n🔗 {c['link']}"
            try:
                await context.bot.send_message(user_id, msg, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Erro envio {user_id}: {e}")
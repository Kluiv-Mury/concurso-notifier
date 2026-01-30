import json

def salvar_usuario(chat_id):
    try:
        with open("usuarios.json", "r") as f:
            usuarios = json.load(f)
    except FileNotFoundError:
        usuarios = []

    if chat_id not in usuarios:
        usuarios.append(chat_id)
        with open("usuarios.json", "w") as f:
            json.dump(usuarios, f)


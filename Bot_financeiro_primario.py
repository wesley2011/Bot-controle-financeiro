import os
import json
import hashlib
import threading
import schedule
import time
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from dateutil.relativedelta import relativedelta
import requests
import telegram
from telegram import (
    Update,
    Bot,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    ParseMode,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    Filters,
    ConversationHandler,
    RegexHandler,
)
from mega import Mega
import logging
from logging.handlers import RotatingFileHandler
import locale

LOGIN_MEGA = "LOGIN MEGA.NZ"
SENHA_MEGA = "senha mega.nz"
TOKEN_BOT = "TOKEN DO BOT"
# Define o caminho absoluto para o arquivo de log
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot.log')

# Configuração do log
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

# Criação do diretório para o arquivo de log, se não existir
log_directory = os.path.dirname(log_file_path)
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Criação do handler para o arquivo de log
file_handler = RotatingFileHandler(log_file_path, maxBytes=10*1024*1024, backupCount=5)  # Arquivo com até 10 MB e até 5 arquivos de backup
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Obtém o logger e adiciona o handler
logger = logging.getLogger(__name__)
logger.addHandler(file_handler)

# Criação do logger específico para o módulo apscheduler.scheduler
scheduler_logger = logging.getLogger('apscheduler.scheduler')
scheduler_logger.addHandler(file_handler)


id_da_message = 0
RECEBENDO_ESCOLHA_DIVIDA_A_EXCLUIR = 1
CATEGORIA, DATA_INICIO, DATA_PRIMEIRA_PARCELA, VALOR_TOTAL, QUANTIDADE_PARCELAS, CARTAO_CREDITO, CONFIRMAR_CADASTRO, EDITAR_ITEM, CONFIRMAR_EDICAO, RECEBER_NOVO_VALOR = range(10)
ESCOLHER_PARCELA, PAGAR_PARCELA = range(2)
OPCAO_PAGAMENTO = range(1) 
SELECTING_PARCELA = 1
UPLOADING = 1
MULTIPLOS_CADASTROS, IMPORTAR_PLANILHA = range(2)

# Diretório dos arquivos .json dos usuários
DIRETORIO_USUARIOS = 'Cadastros/'

# Constantes para a conversação
DIGITE_MENSAGEM = 1

# Estados de conversa para o ConversationHandler calculo aluguel.
INICIO = 1
OBTER_VALOR_ALUGUEL = 2
OBTER_VALOR_PAGO = 3
OBTER_DATA_VENCIMENTO = 4

# Diretório dos arquivos .json a serem feitos backup
DIRETORIO_CADASTROS = DIRETORIO_USUARIOS

# Dicionário para armazenar o hash dos dados de cada arquivo .json e o timestamp do último backup
HASHES_ANTERIORES = {}
DIRETORIO_MEGA = 'Cadastros Financeiro Bot'
MENSAGEM_USUARIO = ""
id_mensagem_usuario = None
last_message_id = None


# Handler para o comando /mensagem
def mensagem(update, context):
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    if chat_type == 'private' and chat_id == 381043536:
        context.bot.send_message(chat_id=update.effective_chat.id, text='Escreva a mensagem a ser enviada:')
        return DIGITE_MENSAGEM
    else:
        update.message.reply_text("Somente o @digitandoo tem permissão para esse comando!")
        return False


# Handler para receber a mensagem digitada pelo usuário
def receber_mensagem(update, context):
    mensagem = update.message.text

    escolha = update.message.text.strip().lower()
    if escolha == "cancelar":
        cancelar_operacao(update, context)
        return ConversationHandler.END
    
    try:
        # Listar os arquivos .json de usuários
        arquivos_usuarios = [arquivo for arquivo in os.listdir(DIRETORIO_USUARIOS) if arquivo.endswith('.json')]

        if not arquivos_usuarios:
            context.bot.send_message(chat_id=update.effective_chat.id, text='Não há usuários cadastrados.')
            return

        # Enviar a mensagem para todos os usuários
        usuarios_enviados = []
        mensagem_formatada = f"◈ • ══─━━── • ──━━─══ • ◈\n                  ***Informativo***\n◈ • ══─━━── • ──━━─══ • ◈\n\n"
        for arquivo_usuario in arquivos_usuarios:
            usuario_id = os.path.splitext(arquivo_usuario)[0]  # Obter o ID do usuário a partir do nome do arquivo
            usuarios_enviados.append(usuario_id)
            
            
            mensagem_formatada += mensagem

            context.bot.send_message(chat_id=usuario_id, text=mensagem_formatada, parse_mode=ParseMode.MARKDOWN)

        # Enviar a mensagem de confirmação com a lista de usuários
        mensagem_confirmacao = f"Mensagem enviada para {len(usuarios_enviados)} usuários, segue abaixo a lista:\n"
        mensagem_confirmacao += "\n".join(f"[Usuario Nº - {i + 1}](tg://user?id={user_id})" for i, user_id in enumerate(usuarios_enviados))

        context.bot.send_message(chat_id=update.effective_chat.id, text=mensagem_confirmacao, parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    except Exception as e:
    # Registrar a exceção no log com nível CRITICAL
        logging.exception(f"Ocorreu um erro - /mensagem - {e}")


def criar_planilha(update, context):
    chat_id = update.message.chat_id
    chat_type = update.effective_chat.type
    
    if not chat_type == 'private':
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False

    file_name = f"Cadastros/{chat_id}.xlsx"

    # Cria o arquivo Excel
    workbook = pd.DataFrame(columns=[
        "Categoria",
        "Data de Início",
        "Data da Primeira Parcela",
        "Valor Total",
        "Quantidade de Parcelas",
        "Cartão de Crédito"
    ])
    workbook.to_excel(file_name, index=False)
  
    # Envia a planilha para o chat
    context.bot.send_document(chat_id=chat_id, document=open(file_name, "rb"))
    update.message.reply_text(f"Baixe está planilha no seu computador ou celular, preencha com suas dividas, mantenha o nome do cabeçalho e nao inverta a estrutura.\n\nMantenha o padrão da data no formato DD/MM/AAAA.\n\nQuando preencher a planilha salve ela e de o comando /importar_planilha")

    os.remove(file_name)
    return ConversationHandler.END


def cancelar_importacao(update, context):
    chat_id = update.message.chat_id
    context.bot.send_message(chat_id=chat_id, text="Importação de planilha cancelada.")
    return ConversationHandler.END

def cadastrar_despesa(cadastro, categoria, data_inicio, data_primeira_parcela, valor_total, quantidade_parcelas, cartao_credito):
    # Verifica se as datas estão no formato correto (DD/MM/AAAA)
    try:
        data_inicio = datetime.strptime(str(data_inicio), "%Y-%m-%d %H:%M:%S")
        data_primeira_parcela = datetime.strptime(str(data_primeira_parcela), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False

    # Realiza o cadastro da despesa
    despesa = {
        "Data Cadastro": datetime.now().strftime("%d/%m/%Y"),
        "categoria": categoria,
        "data_inicio": data_inicio.strftime("%d/%m/%Y"),
        "data_primeira_parcela": data_primeira_parcela.strftime("%d/%m/%Y"),
        "valor_total": valor_total,
        "quantidade_parcelas": quantidade_parcelas,
        "cartao_credito": cartao_credito,
        "despesa_paga": False
    }

    # Adiciona a despesa à lista apropriada (diária ou mensal)
    if quantidade_parcelas > 1:
        cadastro["despesas_mensais"].append(despesa)
    else:
        cadastro["despesas_diarias"].append(despesa)

    return True

def importar_planilha(update, context):
    chat_type = update.effective_chat.type
    
    if not chat_type == 'private':
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False

    # Solicita que o usuário envie a planilha
    context.bot.send_message(chat_id=update.message.chat_id, text="Por favor, envie a planilha de despesas no formato Excel.")

    return UPLOADING

def process_spreadsheet(update, context):
    locale.setlocale(locale.LC_ALL, '')
    
    # Verifica se uma planilha foi enviada
    if not update.message.document:
        update.message.reply_text("Por favor, envie uma planilha válida.")
        return UPLOADING
    
 
 
    file = context.bot.get_file(update.message.document.file_id)
    file_path = os.path.join("uploads", os.path.basename(file.file_path))
    
    # Cria o diretório "uploads" se não existir
    os.makedirs("uploads", exist_ok=True)
    
    file.download(file_path)

    try:
        df = pd.read_excel(file_path)
        processing_message = update.message.reply_text("Processando...", reply_markup=ReplyKeyboardRemove())
    
        required_columns = ["Categoria", "Data de Início", "Data da Primeira Parcela", "Valor Total", "Quantidade de Parcelas", "Cartão de Crédito"]
        if not all(col in df.columns for col in required_columns):
            update.message.reply_text("A planilha enviada não possui todas as colunas necessárias.")
            return UPLOADING

        chat_id = update.effective_chat.id
        arquivo_json = f"Cadastros/{chat_id}.json"
        if os.path.exists(arquivo_json):
            with open(arquivo_json, "r") as file:
                cadastro = json.load(file)
        else:
            cadastro = {"despesas_diarias": [], "despesas_mensais": []}

        despesas_invalidas = []
        for index, row in df.iterrows():
            categoria = row["Categoria"]
            data_inicio = row["Data de Início"]
            data_primeira_parcela = row["Data da Primeira Parcela"]
            valor_total = row["Valor Total"]
            quantidade_parcelas = row["Quantidade de Parcelas"]
            cartao_credito = row["Cartão de Crédito"]

            cadastrado = cadastrar_despesa(cadastro, categoria, data_inicio, data_primeira_parcela, valor_total, quantidade_parcelas, cartao_credito)

            if not cadastrado:
                despesas_invalidas.append(f"Linha {index+2}: {categoria}")

        relatorio_despesas_invalidas = ""
        if despesas_invalidas:
            relatorio_despesas_invalidas += "As seguintes despesas não puderam ser cadastradas:\n"
            relatorio_despesas_invalidas += "\n".join(despesas_invalidas)

        with open(arquivo_json, "w") as file:
            json.dump(cadastro, file, ensure_ascii=False, indent=4)
        
        # apaga a mensagem anterior
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
        mensagem = "┃➲ Dados importados:\n"

        for despesa in cadastro["despesas_diarias"]:
            mensagem += f"•┌───────────────\n"
            mensagem += f"•╞─ **Categoria:** `{despesa['categoria']}`\n"
            mensagem += f"•╞─ **Data de Início:** `{despesa['data_inicio']}`\n"
            mensagem += f"•╞─ **Data da Primeira Parcela:** `{despesa['data_primeira_parcela']}`\n"
            mensagem += f"•╞─ **Valor Total:** `{locale.format_string('R$ %.2f', despesa['valor_total'], grouping=True)}`\n"
            mensagem += f"•╞─ **Quantidade de Parcelas:** `{despesa['quantidade_parcelas']}`\n"
            mensagem += f"•╞─ **Forma de Pagamento:** `{despesa['cartao_credito']}`\n"
            mensagem += f"•└───────────────\n"



        for despesa in cadastro["despesas_mensais"]:
            mensagem += f"•┌───────────────\n"
            mensagem += f"•╞─ **Categoria:** `{despesa['categoria']}`\n"
            mensagem += f"•╞─ **Data de Início:** `{despesa['data_inicio']}`\n"
            mensagem += f"•╞─ **Data da Primeira Parcela:** `{despesa['data_primeira_parcela']}`\n"
            mensagem += f"•╞─ **Valor Total:** `{locale.format_string('R$ %.2f', despesa['valor_total'], grouping=True)}`\n"
            mensagem += f"•╞─ **Quantidade de Parcelas:** `{despesa['quantidade_parcelas']}`\n"
            mensagem += f"•╞─ **Forma de Pagamento:** `{despesa['cartao_credito']}`\n"
            mensagem += f"•└───────────────\n"


        context.bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)
        update.message.reply_text(mensagem, parse_mode=telegram.ParseMode.MARKDOWN)

        os.remove(file_path)
        if relatorio_despesas_invalidas:
            update.message.reply_text(relatorio_despesas_invalidas)
    except Exception as e:
        update.message.reply_text("Ocorreu um erro ao processar a planilha. Por favor, tente novamente.")
        print(e)

    return ConversationHandler.END

def iniciar_cadastro_despesa(update, context):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    if not chat_type == 'private':
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False

    context.chat_data['cadastro_temporario'] = {}  # Dados temporários do cadastro

    # Solicita a categoria da despesa
    update.message.reply_text("Por favor, informe o nome da despesa:")
    return CATEGORIA

def receber_categoria_despesa(update, context):
    categoria = update.message.text
    context.chat_data['cadastro_temporario']['Data Cadastro'] = datetime.now().strftime("%d/%m/%Y")
    context.chat_data['cadastro_temporario']['categoria'] = categoria

    # Solicita a data de início da despesa
    update.message.reply_text("Por favor, informe a data de início da despesa (DD/MM/AAAA):")
    return DATA_INICIO

def receber_data_inicio_despesa(update, context):
    data_inicio = update.message.text
    try:
        date_obj = datetime.strptime(data_inicio, "%d/%m/%Y").date()  # Verifica se a data está no formato correto
        if date_obj.year < 1000:
            # Adjust the year if it is in two-digit format
            current_year = datetime.now().year
            century = current_year // 100  # Extract the century from the current year
            date_obj = date_obj.replace(year=century * 100 + date_obj.year)  # Set the full year
        context.chat_data['cadastro_temporario']['data_inicio'] = date_obj.strftime("%d/%m/%Y")
        # Solicita a data da primeira parcela
        update.message.reply_text("Por favor, informe a data da primeira parcela (DD/MM/AAAA):")
        return DATA_PRIMEIRA_PARCELA
    except ValueError:
        update.message.reply_text("A data informada está em um formato inválido. Por favor, informe a data no formato DD/MM/AAAA.")
        return DATA_INICIO

def receber_data_primeira_parcela(update, context):
    data_primeira_parcela = update.message.text
    try:
        date_obj = datetime.strptime(data_primeira_parcela, "%d/%m/%Y").date()  # Verifica se a data está no formato correto
        if date_obj.year < 1000:
            # Adjust the year if it is in two-digit format
            current_year = datetime.now().year
            century = current_year // 100  # Extract the century from the current year
            date_obj = date_obj.replace(year=century * 100 + date_obj.year)  # Set the full year
        context.chat_data['cadastro_temporario']['data_primeira_parcela'] = date_obj.strftime("%d/%m/%Y")
        # Solicita o valor total da despesa
        update.message.reply_text("Por favor, informe o valor total da despesa (ex: 13.50):")
        return VALOR_TOTAL
    except ValueError:
        update.message.reply_text("A data informada está em um formato inválido. Por favor, informe a data no formato DD/MM/AAAA.")
        return DATA_PRIMEIRA_PARCELA

def receber_valor_total_despesa(update, context):
    valor_total = update.message.text
    context.chat_data['cadastro_temporario']['valor_total'] = float(valor_total)
    
    # Solicita a quantidade de parcelas
    update.message.reply_text("Por favor, informe a quantidade de parcelas:")
    return QUANTIDADE_PARCELAS

def receber_quantidade_parcelas(update, context):
    quantidade_parcelas = update.message.text
    context.chat_data['cadastro_temporario']['quantidade_parcelas'] = int(quantidade_parcelas)

    # Solicita a forma de pagamento (cartão de crédito)
    update.message.reply_text("Por favor, informe a forma de pagamento (cartão, boleto ou pix):")
    return CARTAO_CREDITO

def receber_cartao_credito(update, context):
    chat_id = update.message.chat_id
    cartao_credito = update.message.text
    context.chat_data['cadastro_temporario']['cartao_credito'] = cartao_credito
    context.chat_data['cadastro_temporario']['despesa_paga'] = False
    # Exibe os dados preenchidos para confirmação
    message = "•┌─ Confirme os dados do cadastro:\n"
    message += f"•╞\n"
    message += f"•╞─ **Categoria: {context.chat_data['cadastro_temporario']['categoria']}\n"
    message += f"•╞─ **Data de Início: {context.chat_data['cadastro_temporario']['data_inicio']}\n"
    message += f"•╞─ **Data da Primeira Parcela: {context.chat_data['cadastro_temporario']['data_primeira_parcela']}\n"
    message += f"•╞─ **Valor Total: {context.chat_data['cadastro_temporario']['valor_total']}\n"
    message += f"•╞─ **Quantidade de Parcelas: {context.chat_data['cadastro_temporario']['quantidade_parcelas']}\n"
    message += f"•╞─ **Forma de Pagamento: {context.chat_data['cadastro_temporario']['cartao_credito']}\n"
    message += f"•└───────────────\n\n"
    message += "Deseja cadastrar? (Sim / Não)"

    keyboard = [
        [KeyboardButton("Sim"), KeyboardButton("Não")]
    ]
    context.bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    update.message.reply_text(message, reply_markup=reply_markup, parse_mode=telegram.ParseMode.MARKDOWN)

    return CONFIRMAR_CADASTRO


def confirmar_cadastro_despesa(update, context):
    escolha = update.message.text.lower()
    if escolha == "sim":
        # Finaliza o cadastro
        finalizar_cadastro_despesa(update, context)
        return ConversationHandler.END
    elif escolha == "não":
        # Pergunta se deseja cancelar ou editar
        message = "Deseja cancelar o cadastro ou editar os dados?"
        keyboard = [
            [KeyboardButton("Cancelar"), KeyboardButton("Editar")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text(message, reply_markup=reply_markup)
        return EDITAR_ITEM
    else:
        update.message.reply_text("Escolha inválida. Por favor, escolha 'Sim' ou 'Não'.")
        return CONFIRMAR_CADASTRO

def editar_item_cadastro(update, context):
    escolha = update.message.text.lower()
    if escolha == "cancelar":
        
        processing_message = update.message.reply_text("Processando...", reply_markup=ReplyKeyboardRemove())
        
        # apaga a mensagem anterior
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
    
        update.message.reply_text("Cadastro de despesa cancelado.")
        # Limpa os dados temporários do cadastro
        del context.chat_data['cadastro_temporario']
        return ConversationHandler.END
    elif escolha == "editar":
        # Exibe os dados preenchidos para edição
        message = "Selecione o item que deseja editar:\n\n"
        message += "1. Categoria\n"
        message += "2. Data de Início\n"
        message += "3. Data da Primeira Parcela\n"
        message += "4. Valor Total\n"
        message += "5. Quantidade de Parcelas\n"
        message += "6. Forma de Pagamento\n\n"
        message += "Digite o número correspondente ao item que deseja editar ou digite 'Finalizar' para finalizar o cadastro."

        keyboard = [
            [KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3")],
            [KeyboardButton("4"), KeyboardButton("5"), KeyboardButton("6")],
            [KeyboardButton("Finalizar")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        update.message.reply_text(message, reply_markup=reply_markup)

        return CONFIRMAR_EDICAO

def confirmar_edicao_cadastro(update, context):
    escolha = update.message.text.lower()
    if escolha == "finalizar":
        # Finaliza o cadastro
        
        processing_message = update.message.reply_text("Processando...", reply_markup=ReplyKeyboardRemove())
        
        # apaga a mensagem anterior
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
    
        finalizar_cadastro_despesa(update, context)
        return ConversationHandler.END
    elif escolha in ["1", "2", "3", "4", "5", "6"]:
        # Solicita o novo valor para edição
        context.user_data['item_edicao'] = escolha
        message = "Digite o novo valor para o item selecionado:"
        update.message.reply_text(message)
        return RECEBER_NOVO_VALOR
    else:
        update.message.reply_text("Escolha inválida. Por favor, escolha um item válido ou digite 'Finalizar'.")
        return CONFIRMAR_EDICAO

def receber_novo_valor(update, context):
    novo_valor = update.message.text
    item_edicao = context.user_data['item_edicao']
    # Atualiza o valor do item no cadastro temporário
    if item_edicao == "1":
        context.chat_data['cadastro_temporario']['categoria'] = novo_valor
    elif item_edicao == "2":
        # Verifica se é uma data e ajusta o formato se necessário
        try:
            date_obj = datetime.strptime(novo_valor, "%d/%m/%Y").date()
            if date_obj.year < 1000:
                # Adjust the year if it is in two-digit format
                current_year = datetime.now().year
                century = current_year // 100  # Extract the century from the current year
                date_obj = date_obj.replace(year=century * 100 + date_obj.year)  # Set the full year
            novo_valor = date_obj.strftime("%d/%m/%Y")
            context.chat_data['cadastro_temporario']['data_inicio'] = novo_valor
        except ValueError:
            update.message.reply_text("A data informada está em um formato inválido. Por favor, informe a data no formato DD/MM/AAAA.")
            return CONFIRMAR_EDICAO

    elif item_edicao == "3":
        # Verifica se é uma data e ajusta o formato se necessário
        try:
            date_obj = datetime.strptime(novo_valor, "%d/%m/%Y").date()
            if date_obj.year < 1000:
                # Adjust the year if it is in two-digit format
                current_year = datetime.now().year
                century = current_year // 100  # Extract the century from the current year
                date_obj = date_obj.replace(year=century * 100 + date_obj.year)  # Set the full year
            novo_valor = date_obj.strftime("%d/%m/%Y")
            context.chat_data['cadastro_temporario']['data_primeira_parcela'] = novo_valor
        except ValueError:
            update.message.reply_text("A data informada está em um formato inválido. Por favor, informe a data no formato DD/MM/AAAA.")
            return CONFIRMAR_EDICAO
    elif item_edicao == "4":
        context.chat_data['cadastro_temporario']['valor_total'] = float(novo_valor)
    elif item_edicao == "5":
        context.chat_data['cadastro_temporario']['quantidade_parcelas'] = int(novo_valor)
    elif item_edicao == "6":
        context.chat_data['cadastro_temporario']['cartao_credito'] = novo_valor

    # Exibe os dados atualizados para confirmação
    message = "Confirme os dados do cadastro:\n\n"
    message += f"•┌───────────────\n"
    message += f"•╞─ ***Categoria:*** `{context.chat_data['cadastro_temporario']['categoria']}`\n"
    message += f"•╞─ ***Data de Início:*** `{context.chat_data['cadastro_temporario']['data_inicio']}`\n"
    message += f"•╞─ ***Data da Primeira Parcela:*** `{context.chat_data['cadastro_temporario']['data_primeira_parcela']}`\n"
    message += f"•╞─ ***Valor Total:*** `{context.chat_data['cadastro_temporario']['valor_total']}`\n"
    message += f"•╞─ ***Quantidade de Parcelas:*** `{context.chat_data['cadastro_temporario']['quantidade_parcelas']}`\n"
    message += f"•╞─ ***Forma de Pagamento:*** `{context.chat_data['cadastro_temporario']['cartao_credito']}`\n"
    message += f"•└───────────────\n\n"

    message += "Deseja cadastrar? (Sim / Não)"

    keyboard = [
        [KeyboardButton("Sim"), KeyboardButton("Não")]
    ]
    reply_markup =ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(message, reply_markup=reply_markup, parse_mode=telegram.ParseMode.MARKDOWN)
    return CONFIRMAR_CADASTRO

def finalizar_cadastro_despesa(update, context):
    locale.setlocale(locale.LC_ALL, '')
    chat_id = update.effective_chat.id

    processing_message = update.message.reply_text("Processando...", reply_markup=ReplyKeyboardRemove())
    
    # apaga a mensagem anterior
    context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
   

    # Obtém o cadastro temporário
    cadastro_temporario = context.chat_data['cadastro_temporario']

    # Verifica se o usuário tem um arquivo JSON de cadastro
    arquivo_json = f"Cadastros/{chat_id}.json"
    if os.path.exists(arquivo_json):
        # Carrega o arquivo JSON
        with open(arquivo_json, "r") as file:
            cadastro = json.load(file)
    else:
        cadastro = {"despesas_diarias": [], "despesas_mensais": [], "rendas_mensais": []}

    # Adiciona a despesa à lista apropriada (diária ou mensal)
    if cadastro_temporario['quantidade_parcelas'] > 1:
        cadastro["despesas_mensais"].append(cadastro_temporario)
    else:
        cadastro["despesas_diarias"].append(cadastro_temporario)

    # Salva o cadastro atualizado no arquivo JSON
    with open(arquivo_json, "w") as file:
        json.dump(cadastro, file, ensure_ascii=False, indent=4)

    # Exibe os dados cadastrados
    message = "Despesa cadastrada com sucesso!\n\n"
    message += f"•┌──────── ***Dados cadastrados:***\n"
    message += f"•╞─ ***Categoria:*** `{cadastro_temporario['categoria']}`\n"
    message += f"•╞─ ***Data de Início:*** `{cadastro_temporario['data_inicio']}`\n"
    message += f"•╞─ ***Data da Primeira Parcela:*** `{cadastro_temporario['data_primeira_parcela']}`\n"
    message += f"•╞─ ***Valor Total:*** `{locale.format_string('R$ %.2f', cadastro_temporario['valor_total'], grouping=True)}`\n"
    message += f"•╞─ ***Quantidade de Parcelas:*** `{cadastro_temporario['quantidade_parcelas']}`\n"
    message += f"•╞─ ***Forma de Pagamento:*** `{cadastro_temporario['cartao_credito']}`\n"
    message += f"•└───────────────\n\n\n"
    
    update.message.reply_text(message, parse_mode=telegram.ParseMode.MARKDOWN)
    # Limpa os dados temporários do cadastro
    del context.chat_data['cadastro_temporario']
    update.message.reply_text(f"Para mais informação use /help", parse_mode=telegram.ParseMode.MARKDOWN)

def cancelar_cadastro_despesa(update, context):
    update.message.reply_text("Cadastro de despesa cancelado.", reply_markup=ReplyKeyboardRemove())
    print(f"Cadastrado Cancelado.")
    # Limpa os dados temporários do cadastro
    del context.chat_data['cadastro_temporario']
    return ConversationHandler.END

def get_col_widths(dataframe):
    col_widths = []
    for col in dataframe.columns:
        max_length = max(
            dataframe[col].astype(str).map(len).max(),
            len(col)
        )
        col_widths.append(max_length)
    return col_widths

def formatar_data(data):
    return pd.to_datetime(data, format="%d/%m/%Y").strftime("%d/%m/%Y %H:%M:%S")

def exibir_relatorio(update, context):
    update.message.reply_text('/relatorio_excel - Temporariamente Desabilitado!')

def relatorio_resumido(update, context):
    chat_type = update.effective_chat.type
    
    if not chat_type == 'private':
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False

    locale.setlocale(locale.LC_ALL, '')
    chat_id = update.message.chat_id
    cadastro = carregar_cadastro(chat_id)
    context.bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)
    
    despesas_diarias = cadastro.get('despesas_diarias', [])
    despesas_mensais = cadastro.get('despesas_mensais', [])

    if not despesas_diarias and not despesas_mensais:
        update.message.reply_text("Sinto muito mas não há despesas cadastradas.")
        return

    message = "***Relatório de Despesas:***\n\n"
    notificacao_diaria = 0
    notificacao_mensal = 0

    if despesas_diarias:
        message += "***Despesas Diárias:*** `(possue apenas 1 parcela)`\n\n"
        for i, despesa in enumerate(despesas_diarias, 1):
            categoria = despesa['categoria']
            quantidade_parcelas = despesa['quantidade_parcelas']
            despesa_paga = despesa['despesa_paga']
            historico_pagamentos = despesa.get('historico_pagamentos', [])
            valor_total = despesa['valor_total']
            
            if historico_pagamentos:
                parcela_pendete = quantidade_parcelas
                parcela_paga = len(historico_pagamentos)
            else:
                parcela_pendete = quantidade_parcelas

            if historico_pagamentos:
                mensal_parcela = valor_total / historico_pagamentos[0]['parcela']
                valor_pago = valor_total / historico_pagamentos[0]['parcela'] * len(historico_pagamentos)
                valor_pendente_mes = mensal_parcela if len(historico_pagamentos) < quantidade_parcelas else 0
                total_meses = valor_total - valor_pago
                if 0 < total_meses:
                    valor_total_meses = total_meses                                          
                else:
                    valor_total_meses = 0       
            else:
                if quantidade_parcelas > 0:
                    mensal_parcela = valor_total / quantidade_parcelas
                    valor_pago = mensal_parcela * len(historico_pagamentos)
                else:
                    mensal_parcela = 0
            
            message += f"•┌──────── ***Divida Nº*** - ***{i}***\n"
            message += f"•╞─ ***Categoria:*** `{categoria}`\n"




            if despesa_paga:
                status = "Pago"
                message += f"•╞─ ***Valor Pago:*** `{locale.format_string('R$ %.2f', mensal_parcela, grouping=True)}`\n"
                message += f"•╞───────────────\n"
                message += f"•╞─ ***Situação da divida:*** `{status}`\n"
                if len(historico_pagamentos) > 0:
                    data_pagamento_str = historico_pagamentos[0]['data_pagamento']
                    datas = datetime.strptime(data_pagamento_str, "%d/%m/%Y %H:%M:%S")
                    datas = datas.strftime("%d/%m/%Y")
                    message += f"•╞─ ***Data Pagamento:*** `{datas}`\n"
                else:
                    data_pagamento_str = historico_pagamentos[len(historico_pagamentos)]['data_pagamento']
                    datas = datetime.strptime(data_pagamento_str, "%d/%m/%Y %H:%M:%S")
                    datas = datas.strftime("%d/%m/%Y")
                    message += f"•╞─ ***Data Pagamento:*** `{datas}`\n"
                message += f"•└───────────────\n\n\n"
            else:
                if notificacao_diaria > 0:
                    notificacao_diaria += mensal_parcela
                else:
                    notificacao_diaria += mensal_parcela
                status = "Pendente"
                message += f"•╞─ ***Situação da divida:*** `{status}`\n"
                message += f"•╞─ ***Valor Parcela:*** `{locale.format_string('R$ %.2f', mensal_parcela, grouping=True)}`\n"
                if not historico_pagamentos:
                    message += f"•╞─ ***Parcelas Pendentes:*** `{parcela_pendete}`\n"
                    message += f"•╞─ ***Data de vencimento:*** `{despesa['data_primeira_parcela']}`\n"
                    message += f"•└───────────────\n"


                        

        context.bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)
        update.message.reply_text(message, parse_mode=telegram.ParseMode.MARKDOWN)

        message = ""
    if despesas_mensais:
        message += "\n***Despesas Mensais:*** `(Possue mais de 2 parcela)`\n\n"
        for i, despesa in enumerate(despesas_mensais, 1):
            categoria = despesa['categoria']
            quantidade_parcelas = despesa['quantidade_parcelas']
            despesa_paga = despesa['despesa_paga']
            historico_pagamentos = despesa.get('historico_pagamentos', [])
            valor_total = despesa['valor_total']

            if historico_pagamentos:
                parcela_pendete = quantidade_parcelas
                parcela_paga = len(historico_pagamentos)
            else:
                parcela_pendete = quantidade_parcelas

            if historico_pagamentos:
                mensal_parcela = valor_total / historico_pagamentos[0]['parcela']
                valor_pago = valor_total / historico_pagamentos[0]['parcela'] * len(historico_pagamentos)
                valor_pendente_mes = mensal_parcela if len(historico_pagamentos) < quantidade_parcelas else 0
                total_meses = valor_total - valor_pago
                if 0 < total_meses:
                    valor_total_meses = total_meses                                          
                else:
                    valor_total_meses = 0       
            else:
                if quantidade_parcelas > 0:
                    mensal_parcela = valor_total / quantidade_parcelas
                    valor_pago = mensal_parcela * len(historico_pagamentos)
                else:
                    mensal_parcela = 0


                
            
            message += f"•┌──────── ***Divida Nº*** - ***{i}***\n"
            message += f"•╞─ ***Categoria:*** `{categoria}`\n"


            if despesa_paga:
                status = "Pago"
                message += f"•╞─ ***Valor Pago:*** `{locale.format_string('R$ %.2f', mensal_parcela, grouping=True)}`\n"
                message += f"•╞───────────────\n"
                message += f"•╞─ ***Situação da divida:*** `{status}`\n"
                if len(historico_pagamentos) > 0:
                    data_pagamento_str = historico_pagamentos[0]['data_pagamento']
                    datas = datetime.strptime(data_pagamento_str, "%d/%m/%Y %H:%M:%S")
                    datas = datas.strftime("%d/%m/%Y")
                    message += f"•╞─ ***Data Pagamento:*** `{datas}`\n"
                else:
                    data_pagamento_str = historico_pagamentos[len(historico_pagamentos)]['data_pagamento']
                    datas = datetime.strptime(data_pagamento_str, "%d/%m/%Y %H:%M:%S")
                    datas = datas.strftime("%d/%m/%Y")
                    message += f"•╞─ ***Data Pagamento:*** `{datas}`\n"

                message += f"•└───────────────\n\n\n"
            else:
                if notificacao_mensal > 0:
                    notificacao_mensal += mensal_parcela
                else:
                    notificacao_mensal += mensal_parcela
                status = "Pendente"
                message += f"•╞─ ***Situação da divida:*** `{status}`\n"
                message += f"•╞─ ***Valor Parcela:*** `{locale.format_string('R$ %.2f', mensal_parcela, grouping=True)}`\n"
                if not historico_pagamentos:
                    message += f"•╞─ ***Parcelas Pendentes:*** `{parcela_pendete}`\n"
                    message += f"•╞─ ***Data de vencimento:*** `{despesa['data_primeira_parcela']}`\n"
                    message += f"•└───────────────\n"
                else:
                    message += f"•╞─ ***Parcelas Pendentes:*** `{parcela_pendete}`\n"
                    message += f"•╞─ ***Parcelas Pagas:*** `{parcela_paga}`\n"
   
   
                if historico_pagamentos:
                    message += f"•╞───────────────\n"
                    message += f"•╞─ ***Data de vencimento:*** `{despesa['data_primeira_parcela']}`\n"
                    message += f"•╞─ ***Valor a pagar:*** `{locale.format_string('R$ %.2f', valor_pendente_mes, grouping=True)}`\n"
                    message += f"•╞───────────────\n"
                    message += f"•╞─ ***Valor Pago:*** `{locale.format_string('R$ %.2f', valor_pago, grouping=True)}`\n"
                    message += f"•╞─ ***Saldo devedor:*** `{locale.format_string('R$ %.2f', valor_total_meses, grouping=True)}`\n"
                    message += f"•└───────────────\n\n\n"

        context.bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)
        update.message.reply_text(message, parse_mode=telegram.ParseMode.MARKDOWN)

        info = f"Segue abaixo os valor a ser pago, somando as parcelas.\n"
        print(f"usuario: {update.message.from_user.first_name} -  ID: {chat_id} - Resultado: Diaria")
        print("Total despesa diaria: ",len(despesas_diarias))
        print("Total despesa diaria: ",len(despesas_mensais))
        if notificacao_diaria > 0:
            print(f"Total Parcelas a pagar -> {notificacao_diaria}")
            info += f"•┌───────────────\n"
            info += f"•╞─ ***Total com 1 parcela (diaria):***\n"
            info += f"•╞─ ***Valor: {locale.format_string('R$ %.2f', notificacao_diaria, grouping=True)}***\n"
            if notificacao_mensal > 0:
                info += f"•╞───────────────\n"
            else:
                info += f"•└───────────────\n"
        else:
            info += f"•┌───────────────\n"

        if notificacao_mensal > 0:
            print(f"Total Parcelas a pagar -> {notificacao_mensal}")
            info += f"•╞─ ***Total com + de 2 parcela (mensal)***\n"
            info += f"•╞─ ***Valor: {locale.format_string('R$ %.2f', notificacao_mensal, grouping=True)}***\n"
            info += f"•└───────────────\n"

        info += f"•┌───────────────\n"
        info += f"•╞─ ***Total: {locale.format_string('R$ %.2f', (notificacao_mensal + notificacao_diaria), grouping=True)}***\n"
        info += f"•└───────────────\n"
        print("---------------------------------")


        update.message.reply_text(info, parse_mode=telegram.ParseMode.MARKDOWN)
        messagem = f"Relatorio finalizado, se te ajudo em algo mais use o comando /help"
        context.bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)
        context.bot.send_message(chat_id=chat_id, text=messagem, parse_mode=ParseMode.MARKDOWN)

def carregar_cadastro(chat_id):
    arquivo_json = f"Cadastros/{chat_id}.json"
    if os.path.exists(arquivo_json):
        with open(arquivo_json, "r") as file:
            try:
                cadastro = json.load(file)
                return cadastro
            except json.decoder.JSONDecodeError as e:
                print("Erro na decodificação do JSON:", str(e))
                return {}
    else:
        print("Arquivo JSON não encontrado:", arquivo_json)
        return {}

def salvar_cadastro(chat_id, cadastro):
    arquivo_json = f"Cadastros/{chat_id}.json"
    print(f"chat_id: {chat_id}")
    with open(arquivo_json, "w") as file:
        json.dump(cadastro, file, ensure_ascii=False, indent=4)
        print("Cadastro salvo:", cadastro)

def escolher_parcela(update, context):
    locale.setlocale(locale.LC_ALL, '')
    chat_id = update.message.chat_id
    chat_type = update.effective_chat.type
    
    if not chat_type == 'private':
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False


    cadastro = carregar_cadastro(chat_id)

    despesas_diarias = cadastro.get('despesas_diarias', [])
    despesas_mensais = cadastro.get('despesas_mensais', [])

    todas_despesas = despesas_diarias + despesas_mensais

    if todas_despesas:
        message = ""
        keyboard = [
                [KeyboardButton("Cancelar")]
            ]
        for index, despesa in enumerate(todas_despesas, 1):
            
            categoria = despesa.get('categoria')
            valor_total = despesa.get('valor_total')
            historico_pagamentos = despesa.get('historico_pagamentos', [])
            status = "PAGA" if despesa.get('despesa_paga', False) else ""
            quantidade_parcelas = despesa.get('quantidade_parcelas', 0)

            if historico_pagamentos:
                mensal_parcela = valor_total / historico_pagamentos[0]['parcela']
                inic = len(historico_pagamentos)
                de = historico_pagamentos[0]['parcela']           
            else:
                mensal_parcela = valor_total / quantidade_parcelas
                inic = 1
                de = quantidade_parcelas
                
            if index == 1:
                message += f"┌─ ***Nº {index}***\n"
            else:
                message += f"├─ ***Nº {index}***\n"

            if despesa.get('despesa_paga') == False:

                message += f"├─ ***Dívida:*** ```{categoria}```\n"
                message += f"├─ ***Valor a pagar:*** `{mensal_parcela}`\n"
                message += f"├─ ***Parcela: {inic} de {de}***\n"
                if index == len(todas_despesas):
                    message += f"└───────────────\n"
                    message += f"\n Selecione o numero correspondente ou aperte 'Cancelar'"
                else:
                    message += f"├───────────────\n"
            else:
                message += f"├─ ***Dívida:*** ```{categoria}```\n"
                message += f"├─ ***Status: {status}***\n"
                if index == len(todas_despesas):
                    message += f"└───────────────\n"
                    message += f"\n Selecione o numero correspondente ou aperte 'Cancelar'"
                else:
                    message += f"├───────────────\n"


            if despesa.get('despesa_paga') == False:
                keyboard.append([f"{index}. ── Dívida: {categoria}"])
        global id_da_message
        id_da_message = update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True, selective=True), parse_mode=telegram.ParseMode.MARKDOWN)

        context.user_data['todas_despesas'] = todas_despesas
        return SELECTING_PARCELA

    update.message.reply_text("Nenhuma despesa encontrada.")
    return ConversationHandler.END

def pagar_parcela(update, context):
    global id_da_message
    
    chat_id = update.message.chat_id
    escolha = update.message.text.strip().lower()
    if escolha == "cancelar":
        cancelar_operacao(update, context)
        return ConversationHandler.END

    cadastro_temporario = context.chat_data.get('cadastro_temporario', {})
    todas_despesas = context.user_data.get('todas_despesas', [])
    processing_message = update.message.reply_text("Processando...", reply_markup=ReplyKeyboardRemove())
    context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)

    
    # Armazena o ID da mensagem enviada pelo bot//
   # bot_message_id = processing_message.message_id
    arquivo_json = f"Cadastros/{chat_id}.json"
    with open(arquivo_json, "r") as file:
        dados_json = json.load(file)

    despesas_diarias = dados_json.get('despesas_diarias', [])
    despesas_mensais = dados_json.get('despesas_mensais', [])
    todas_despesas = despesas_diarias + despesas_mensais
    try:
        resposta_usuario = update.message.text
        opcao = int(resposta_usuario.split('.')[0].strip())
        if opcao in range(1, len(todas_despesas) + 1):
            despesa = todas_despesas[opcao - 1]
            tipo_despesa = despesa.get('categoria')

            if despesa.get('despesa_paga', False):
                data_pagamento = despesa.get('historico_pagamentos')[-1].get('data_pagamento')
                update.message.reply_text(f"Esta despesa já foi paga em {data_pagamento}. Por favor, tente novamente.")
                return ConversationHandler.END

            # Cria uma nova estrutura da despesa selecionada
            nova_despesa = despesa.copy()

            nova_despesa['quantidade_parcelas'] -= 1
            if nova_despesa['quantidade_parcelas'] == 0:
                nova_despesa['despesa_paga'] = True
            else:
                proxima_data_parcela = calcular_proxima_data_parcela(
                    nova_despesa['data_primeira_parcela'], nova_despesa['quantidade_parcelas']
                )
                
                nova_despesa['data_primeira_parcela'] = proxima_data_parcela

            # Adiciona o histórico de pagamentos
            historico_pagamentos = nova_despesa.get('historico_pagamentos', [])
            historico_pagamentos.append({
                'parcela': despesa['quantidade_parcelas'],
                'data_pagamento': datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            })
            nova_despesa['historico_pagamentos'] = historico_pagamentos

            # Atualiza o arquivo JSON preservando a estrutura existente
            arquivo_json = f"Cadastros/{chat_id}.json"
            with open(arquivo_json, "r") as file:
                dados_json = json.load(file)

            # Atualiza a despesa correspondente no JSON
            for categoria, despesas in dados_json.items():
                if categoria in ["despesas_diarias", "despesas_mensais"] and isinstance(despesas, list):
                    for i, despesa_json in enumerate(despesas):
                        if despesa_json.get('categoria') == tipo_despesa:
                            despesas[i] = nova_despesa
                            break

            # Atualiza os dados no arquivo JSON
            with open(arquivo_json, "w") as file:
                json.dump(dados_json, file, ensure_ascii=False, indent=4)

            with open(arquivo_json, "r") as file:
                dados_json = json.load(file)

            # Substitui a mensagem anterior pela mensagem de confirmação
            
            despesas_diarias = dados_json.get('despesas_diarias', [])
            despesas_mensais = dados_json.get('despesas_mensais', [])
            todas_despesas = despesas_diarias + despesas_mensais
                    
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=id_da_message.message_id)
            if opcao in range(1, len(todas_despesas) + 1):
                despesa = todas_despesas[opcao - 1]
                historico_pagamentos = despesa.get('historico_pagamentos', [])
                valor_total = despesa.get('valor_total')
                mensal_parcela = valor_total / historico_pagamentos[0]['parcela']
                # Constrói a mensagem com os dados da dívida
                if len(historico_pagamentos) == 0:
                    parcela = 1
                else:
                    parcela = len(historico_pagamentos) -1

                message = "╭───── • ◈ • ─────╮\n"
                message += f"                  ***Extrato***\n"
                message += f"╰───── • ◈ • ─────╯\n"
                message += f"├─ ***Categoria:*** `{despesa['categoria']}`\n"
                message += f"├─ ***Valor Pago:*** `{mensal_parcela}`\n"
                message += f"├─ ***Parcela paga:*** `{parcela}`\n"
                message += f"└────────────────"
                          
                # Adicione aqui os outros campos que você deseja exibir
                    # apaga a mensagem anterior
                
                update.message.reply_text(message, parse_mode=telegram.ParseMode.MARKDOWN)

            update.message.reply_text("Parcela paga com sucesso.")
           # context.bot.edit_message_text(text="Parcela paga com sucesso.", chat_id=chat_id, message_id=bot_message_id)

            return ConversationHandler.END
        else:
            print("Opção inválida. Opções válidas:", list(range(1, len(todas_despesas) + 1)))
            update.message.reply_text("Opção inválida. Por favor, selecione uma opção válida.")
            return
    except (ValueError, IndexError):
        print("Resposta inválida. Opções válidas:", list(range(1, len(todas_despesas) + 1)))
        update.message.reply_text("Resposta inválida. Por favor, selecione uma opção válida.")
        return

def calcular_proxima_data_parcela(data_primeira_parcela, quantidade_parcelas):
    data_inicio = datetime.strptime(data_primeira_parcela, '%d/%m/%Y')
    proxima_data_parcela = data_inicio + relativedelta(months=1)
    return proxima_data_parcela.strftime('%d/%m/%Y')

def atualizar_parcelas_pendentes(cadastro):
    despesas_pendentes = []

    for despesa in cadastro.get('despesas_diarias', []):
        if not despesa['despesa_paga']:
            despesas_pendentes.append(('diária', despesa))

    for despesa in cadastro.get('despesas_mensais', []):
        if not despesa['despesa_paga']:
            despesas_pendentes.append(('mensal', despesa))

    despesas_pendentes.sort(key=lambda x: x[1]['data_primeira_parcela'])
    return despesas_pendentes

def cancelar_operacao(update, context):
    update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

def apagar_cadastro(update, context):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    if not chat_type == 'private':
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False

    arquivo_json = f"Cadastros/{chat_id}.json"
    if os.path.exists(arquivo_json):
        # Carrega o arquivo JSON
        with open(arquivo_json, "r") as file:
            cadastro = json.load(file)

        # Cria uma lista com todas as despesas
        despesas_diarias = cadastro.get('despesas_diarias', [])
        despesas_mensais = cadastro.get('despesas_mensais', [])
        todas_despesas = despesas_diarias + despesas_mensais
        if not todas_despesas:
            update.message.reply_text("Nenhuma dívida encontrada!")
            return ConversationHandler.END

        # Monta a lista de dívidas com os dados para o usuário selecionar
        if todas_despesas:
            message = ""
            keyboard = [
                    [KeyboardButton("Cancelar")]
                ]

            for index, despesa in enumerate(todas_despesas, 1):
                
                categoria = despesa.get('categoria')
                valor_total = despesa.get('valor_total')
                historico_pagamentos = despesa.get('historico_pagamentos', [])
                status = "PAGA" if despesa.get('despesa_paga', False) else ""
                quantidade_parcelas = despesa.get('quantidade_parcelas', 0)

                if historico_pagamentos:
                    mensal_parcela = valor_total / historico_pagamentos[0]['parcela']
                    inic = len(historico_pagamentos)
                    de = historico_pagamentos[0]['parcela']           
                else:
                    mensal_parcela = valor_total / quantidade_parcelas
                    inic = 1
                    de = quantidade_parcelas
                    
                if index == 1:
                    message += f"┌─ ***Nº {index}***\n"
                else:
                    message += f"├─ ***Nº {index}***\n"

                if despesa.get('despesa_paga') == False:

                    message += f"├─ ***Dívida:*** ```{categoria}```\n"
                    message += f"├─ ***Valor a pagar:*** `{mensal_parcela}`\n"
                    message += f"├─ ***Parcela: {inic} de {de}***\n"
                    if index == len(todas_despesas):
                        message += f"└───────────────\n"
                        message += f"\n Selecione o numero correspondente ou aperte 'Cancelar'"
                    else:
                        message += f"├───────────────\n"
                else:
                    message += f"├─ ***Dívida:*** ```{categoria}```\n"
                    message += f"├─ ***Status: {status}***\n"
                    if index == len(todas_despesas):
                        message += f"└───────────────\n"
                        message += f"\n Selecione o numero correspondente ou aperte 'Cancelar'"
                    else:
                        message += f"├───────────────\n"


            
                keyboard.append([f"{index}. ── Dívida Nº: {index}"])
            global id_da_message
                    
            id_da_message =update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True, selective=True), parse_mode=telegram.ParseMode.MARKDOWN)

            return RECEBENDO_ESCOLHA_DIVIDA_A_EXCLUIR
    else:
        update.message.reply_text("Nenhum cadastro encontrado!")
        return ConversationHandler.END

def receber_escolha_divida_a_excluir(update, context):

    escolha = update.message.text.strip().lower()
    if escolha == "cancelar":
        cancelar_operacao(update, context)
        return ConversationHandler.END

    id_da_mess = update.message.reply_text("Processando...", reply_markup=ReplyKeyboardRemove())
    arquivo_json = f"Cadastros/{update.effective_chat.id}.json"
    with open(arquivo_json, "r") as file:
        dados_json = json.load(file)

    despesas_diarias = dados_json.get('despesas_diarias', [])
    despesas_mensais = dados_json.get('despesas_mensais', [])
    todas_despesas = despesas_diarias + despesas_mensais
    
    try:
        resposta_usuario = update.message.text
        opcao = int(resposta_usuario.split('.')[0].strip())
        if opcao in range(1, len(todas_despesas) + 1):
            despesa = todas_despesas[opcao - 1]
            categoria = despesa['categoria']
            historico_pagamentos = despesa.get('historico_pagamentos', [])
            status = "PAGA" if despesa.get('despesa_paga', False) else "NÃO PAGA"
            quantidade_parcelas = despesa.get('quantidade_parcelas', 0)

            if historico_pagamentos:
                inic = len(historico_pagamentos)
                de = historico_pagamentos[0]['parcela']           
            else:
                inic = 1
                de = quantidade_parcelas

            # Atualiza os dados removendo a dívida
            if despesa in despesas_diarias:
                despesas_diarias.remove(despesa)
            else:
                despesas_mensais.remove(despesa)

            with open(arquivo_json, "w") as file:
                json.dump(dados_json, file, ensure_ascii=False, indent=4)

            message = "╭───── • ◈ • ─────╮\n"
            message += f"                  ***Extrato***\n"
            message += f"╰───── • ◈ • ─────╯\n"
            message += f"┌────────────────\n"
            message += f"├─ ***Categoria:*** `{categoria}`\n"
            message += f"├────────────────\n"
            message += f"├─ ***Status: {status}***\n"
            message += f"├────────────────\n"
            message += f"├─ ***Parcelas:*** `{inic}` ***de*** `{de}`\n"
            message += f"└────────────────"
            
            global id_da_message    
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=id_da_mess.message_id)
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=id_da_message.message_id)
            update.message.reply_text(message, parse_mode=telegram.ParseMode.MARKDOWN)
            return ConversationHandler.END
        else:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=id_da_mess.message_id)
            update.message.reply_text("Opção inválida. Por favor, selecione uma opção válida.")
            return RECEBENDO_ESCOLHA_DIVIDA_A_EXCLUIR
    except (ValueError, IndexError):
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=id_da_mess.message_id)
        update.message.reply_text("Opção inválida. Por favor, selecione uma opção válida.")
        return RECEBENDO_ESCOLHA_DIVIDA_A_EXCLUIR

def cancelar_operacao(update, context):
    update.message.reply_text("Operação cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END



# Função para obter o índice INPC
def get_inpc():
    url = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        inpc = data[0]['valor']
        return float(inpc)
    return None

# Função para calcular a multa
def calcular_multa(valor_aluguel, valor_pago, data_vencimento):
    multa = 0.1  # Multa de 10% em caso de atraso
    juros_mora = 0.01  # Juros de mora de 1% ao mês

    # Convertendo a data de vencimento para datetime
    data_vencimento = datetime.strptime(data_vencimento, '%d/%m/%Y').date()

    # Calculando a diferença de dias entre a data de vencimento e a data atual
    dias_atraso = (datetime.now().date() - data_vencimento).days

    if dias_atraso > 0:
        # Calculando o valor da multa
        valor_multa = valor_aluguel * multa

        # Calculando o valor dos juros de mora
        valor_juros = valor_aluguel * juros_mora * dias_atraso

        # Totalizando o valor a ser pago, incluindo multa e juros
        total_a_pagar = valor_aluguel + valor_multa + valor_juros

        # Calculando a diferença entre o valor pago e o total a ser pago
        valor_devido = total_a_pagar - valor_pago

        return valor_devido
    else:
        return 0

# Função para iniciar o cálculo da multa
def calcular_multa_start(update: Update, context: CallbackContext) -> int:
    reply_markup = ReplyKeyboardMarkup([["Cancelar"]], one_time_keyboard=True)
    update.message.reply_text(f"Vamos calcular a multa por atraso de aluguel.\n\nCalculos estão definido em 10% multa, 1% multa diaria e Indice INPC\n\nPor favor, digite o valor do aluguel:",
    reply_markup=reply_markup)
    return OBTER_VALOR_ALUGUEL

# Função para coletar o valor do aluguel
def obter_valor_aluguel(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text
    try:
        valor_aluguel = float(user_input)
        update.message.reply_text('Qual é o valor pago pelo inquilino?')
        context.user_data['valor_aluguel'] = valor_aluguel  # Salva o valor do aluguel na memória do bot
        return OBTER_VALOR_PAGO
    except ValueError:
        update.message.reply_text('Por favor, insira um valor numérico válido para o aluguel.')
        return OBTER_VALOR_ALUGUEL

# Função para coletar o valor pago pelo inquilino
def obter_valor_pago(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text
    try:
        valor_pago = float(user_input)
        update.message.reply_text('Qual é a data de vencimento do aluguel (formato: DD/MM/AAAA)?')
        context.user_data['valor_pago'] = valor_pago  # Salva o valor pago pelo inquilino na memória do bot
        return OBTER_DATA_VENCIMENTO
    except ValueError:
        update.message.reply_text('Por favor, insira um valor numérico válido para o pagamento.')
        return OBTER_VALOR_PAGO

# Função para coletar a data de vencimento do aluguel
def obter_data_vencimento(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text
    context.user_data['data_vencimento'] = user_input  # Salva a data de vencimento na memória do bot

    # Obtém os valores salvos na memória do bot
    valor_aluguel = context.user_data['valor_aluguel']
    valor_pago = context.user_data['valor_pago']
    data_vencimento = context.user_data['data_vencimento']

    # Calcula a diferença de dias entre a data de vencimento e a data atual
    dias_atraso = (datetime.now().date() - datetime.strptime(data_vencimento, '%d/%m/%Y').date()).days

    valor_devido = calcular_multa(valor_aluguel, valor_pago, data_vencimento)
    inpc = get_inpc()

    message = "╭───── • ◈ • ─────╮\n"
    message += f"           ***Valor da Multa***\n"
    message += f"╰───── • ◈ • ─────╯\n"
    message += f"┌────────────────\n"
    message += f"├─ • ***Valor Aluguel:*** `R$ {valor_aluguel:.2f}`\n"
    message += f"├─ • ***Valor Pago:*** `R$ {valor_pago:.2f}`\n"
    message += f"├─ • ***Dias de Atraso:*** `{dias_atraso} dias`\n"
    message += f"└────────────────\n"
    if inpc is not None:
        valor_devido_corrigido = valor_devido * (1 + inpc)
        message += f"┌────────────────\n"
        message += f"├─ •• ***Multa com INPC:*** `R$ {valor_devido_corrigido:.2f}`\n"
        message += f"├─ •• ***Índice INPC:*** `{inpc * 100:.2f}%`\n"
        message += f"└────────────────\n"
    else:
        message += f"┌────────────────\n"
        message += f"├─ •• ***Multa sem INPC:*** `R$ {valor_devido:.2f}`\n"
        message += f"└────────────────\n"

    update.message.reply_text(message, parse_mode=telegram.ParseMode.MARKDOWN)
    update.message.reply_text("Obrigado por usar o bot para cálculo de multa por atraso de aluguel!", reply_markup=ReplyKeyboardRemove())
    

    return ConversationHandler.END




def start_help(update, context):
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    if chat_type == 'private':
        message = update.message
        context.bot.send_message(chat_id="381043536", text=f"comando: Start - Usuário: {message.from_user.name}\nID do usuário: {message.from_user.id}\nUsername: {message.from_user.username}")
    else:
        update.message.reply_text("Este comando só pode ser usado em um chat privado.")
        return False

    mess = f"Olá! Bem-vindo(a) {message.from_user.first_name}, sou seu novo controle de finanças pessoal\n" \
           "Essas são as funções disponíveis, apenas no privado:\n\n" \
           "┌───────────────\n" \
           "/cadastrar_divida - Inicia o processo de cadastro de uma nova despesa.\n" \
           "└───────────────\n" \
           "┌───────────────\n" \
           "/pagar_divida - Inicia o processo de pagamento de uma parcela de despesa.\n\n" \
           "/apagar_cadastro - Exclui uma dívida cadastrada.\n" \
           "└───────────────\n" \
           "┌───────────────\n" \
           "/multiplos_cadastros - Cria uma planilha com layout para importar vários cadastros.\n\n" \
           "/importar_planilha - Importa uma planilha para realizar cadastros.\n" \
           "└───────────────\n" \
           "┌───────────────\n" \
           "Desabilitado - Exibe um relatório completo das despesas cadastradas em excel.\n\n" \
           "/relatorio - Exibe um relatório detalhado das despesas cadastradas.\n" \
           "└───────────────\n" \
           "┌───────────────\n" \
           "/calcular_multa - Calcula multa de contrato de aluguel.\n" \
           "Atraso 10%, Diaria 1% e INPC(Índice Nacional de Preços ao Consumidor), Esse índice é calculado mensalmente pelo IBGE\n" \
           "└───────────────\n"    
    

    context.bot.send_message(chat_id=chat_id, text=mess)


def bam_audio(update: Update, context):
    message = update.message
   # context.bot.send_message(chat_id="381043536", text=f"comando: bam - Usuário: {message.from_user.name}\nID do usuário: {message.from_user.id}\nUsername: {message.from_user.username}")

    replicated_message = message.reply_to_message
    
    if replicated_message:
        id_usu = update.message.reply_to_message.from_user.id
        pri_nome = update.message.reply_to_message.from_user.first_name
        usuario = update.message.reply_to_message.from_user.username
        print(usuario)
        if not usuario == "":
            li = f"@{usuario}"
        else:
            li = f"[{pri_nome}](tg://user?id={id_usu}"

        mensaf = f"***Cheguei.. Toma aqui sua punição*** {li}"
        # Se a mensagem foi replicada, responda a ela
        audio_file_id = "AwACAgQAAxkBAAI0JmSksFopTwABY2C5su8wm2jrlZYRLgACCqAAAuQYZAc6AAEMFzoRAAHKLwQ"
        context.bot.send_message(chat_id=update.effective_chat.id, reply_to_message_id=update.message.reply_to_message.message_id, text=mensaf, parse_mode=ParseMode.MARKDOWN)
        context.bot.send_audio(chat_id=update.effective_chat.id, audio=audio_file_id)
    else:
        # Se não foi replicada, envie a resposta normalmente
        audio_file_id = "AwACAgQAAxkBAAI0JmSksFopTwABY2C5su8wm2jrlZYRLgACCqAAAuQYZAc6AAEMFzoRAAHKLwQ"
        context.bot.send_audio(chat_id=message.chat_id, audio=audio_file_id)


# -----------------------------------------------------------------------------------
#    ADICIONADO BACKUP DIA 21/07/2023

def enviar_e_editar_mensagem(texto):
    global id_mensagem_usuario
    global last_message_id
    global MENSAGEM_USUARIO
    bot = Bot(TOKEN_BOT)
    if last_message_id:
        bot.edit_message_text(chat_id=id_mensagem_usuario, message_id=last_message_id, text=texto, parse_mode=telegram.ParseMode.MARKDOWN)
    else:
        message = bot.send_message(chat_id=id_mensagem_usuario, text=texto, parse_mode=telegram.ParseMode.MARKDOWN)
        last_message_id = message.message_id

# Função para calcular o hash de um arquivo .json
def calcular_hash_arquivo(json_file):
    try:
        sha256_hash = hashlib.sha256()
        with open(json_file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except json.decoder.JSONDecodeError as e:
        logging.exception(f"calcular_hash_arquivo() - Erro ao carregar o arquivo JSON '{json_file}': {e}")
        return None


def fazer_backup_arquivos():
    global MENSAGEM_USUARIO
    global id_mensagem_usuario
    global last_message_id
    try:
        # Verificar se a pasta Cadastros existe
        if not os.path.exists(DIRETORIO_CADASTROS):
            os.makedirs(DIRETORIO_CADASTROS)

        # Obter a lista de arquivos .json na pasta Cadastros
        arquivos_json = [f for f in os.listdir(DIRETORIO_CADASTROS) if f.endswith('.json')]
        
        # Login no Mega.nz
        mega = Mega({'verbose': True})
        login_result = mega.login(LOGIN_MEGA, SENHA_MEGA)
        if not login_result:
            logging.exception("fazer_backup_arquivos() - Falha ao fazer login no Mega.nz. Verifique suas credenciais e conexão com a internet.")
            return

        # Nome da pasta no Mega.nz
        mega_folder_name = 'Cadastros Financeiro Bot'
        # Encontrar a pasta no Mega.nz ou criar uma nova pasta
        mega_folder_id = mega.find(mega_folder_name) 
        if not mega_folder_id:
            mega_folder_id = mega.create_folder(mega_folder_name)
            if not mega_folder_id:
                logging.exception(f"fazer_backup_arquivos() - Falha ao criar a pasta '{mega_folder_name}' no Mega.nz.")
                return
            else:
                logging.exception(f"fazer_backup_arquivos() - Pasta '{mega_folder_name}' criada no Mega.nz com sucesso!")

        
        for json_file in arquivos_json:
            data = datetime.now().strftime("%d/%m/%Y") 
            if MENSAGEM_USUARIO == "":
                MENSAGEM_USUARIO += f"***[+] •*** Iniciando backup dos dados cadastrado - {data}\n"
                last_message_id = None
                id_mensagem_usuario = json_file.split('.json')[0]
                enviar_e_editar_mensagem(MENSAGEM_USUARIO)
                
                


            json_path = os.path.join(DIRETORIO_CADASTROS, json_file)
            # Calcular o hash dos dados do arquivo .json
            novo_hash = calcular_hash_arquivo(json_path)

            if json_file not in HASHES_ANTERIORES:
                # Se o arquivo não estiver no dicionário, inicialize com o novo hash
                HASHES_ANTERIORES[json_file] = {'hash': novo_hash, 'file_id': None}
            elif HASHES_ANTERIORES[json_file]['hash'] != novo_hash:
                if existe_no_mega(json_file, mega, mega_folder_id[0]):
                    mega.delete(HASHES_ANTERIORES[json_file]['file_id'])


            if not HASHES_ANTERIORES.get(json_file) or HASHES_ANTERIORES[json_file]['hash'] != novo_hash or not existe_no_mega(json_file, mega, mega_folder_id[0]):
            # Verificar se o arquivo foi modificado desde a última verificação ou se ainda não existe no Mega.nz
                
                with open(json_path, 'r') as file:
                    json_data = json.load(file)

                # Fazer backup do arquivo no Mega.nz e obter o ID do arquivo
                mega_file = fazer_backup_mega(json_path, mega_folder_id[0], mega)
                
                if mega_file:
                    # Atualizar o hash anterior com o novo hash e o ID do arquivo no Mega.nz
                    HASHES_ANTERIORES[json_file] = {'hash': novo_hash, 'file_id': mega_file}

                    # Formatar a mensagem de notificação para o usuário ma

                    MENSAGEM_USUARIO += f"***[+] •*** Concluido!\n"
                    enviar_e_editar_mensagem(MENSAGEM_USUARIO)
                    MENSAGEM_USUARIO = ""
                else:
                    MENSAGEM_USUARIO += f"***[!] •*** Falha ao fazer o backup. contate @digitandoo\n"
                    enviar_e_editar_mensagem(MENSAGEM_USUARIO)
                    MENSAGEM_USUARIO = ""
            else:
                    MENSAGEM_USUARIO += f"***[=] •*** Concluido! Sem alteração.\n"
                    enviar_e_editar_mensagem(MENSAGEM_USUARIO)
                    MENSAGEM_USUARIO = ""

        # Enviar mensagem de notificação do backup realizado
        MENSAGEM_USUARIO = ""
    except Exception as e:
    # Registrar a exceção no log com nível CRITICAL
        logging.exception(f"Ocorreu um erro - fazer_backup_arquivos() - {e}")
        


def fazer_backup_mega(json_file, mega_folder_id, mega):
    global MENSAGEM_USUARIO
    global id_mensagem_usuario

    MENSAGEM_USUARIO += f"***[+] •*** Enviando arquivo para nuvem.\n"
    enviar_e_editar_mensagem(MENSAGEM_USUARIO)
    try:
        # Fazer upload do novo arquivo para a pasta no Mega.nz
        mega_file = mega.upload(json_file, mega_folder_id)

        if mega_file and 'f' in mega_file and mega_file['f']:
            file_id = mega_file['f'][0]['h']
            MENSAGEM_USUARIO += f"***[+] •*** Enviando com sucesso! ID: {file_id}\n"
            enviar_e_editar_mensagem(MENSAGEM_USUARIO)
            return file_id
        else:
            MENSAGEM_USUARIO += f"***[!] •*** Falha ao enviar o arquivo. contate @digitandoo\n"
            enviar_e_editar_mensagem(MENSAGEM_USUARIO)

    except Exception as e:
        logging.exception(f"fazer_backup_mega() - Erro ao fazer o backup do arquivo '{json_file}' no Mega.nz: {e}")
        return None


def existe_no_mega(json_file, mega, mega_folder_id_str):
    try:
        
        files = mega.get_files()
       # ret = mega.find(json_file) # pesquisa o nome do arquivo no mega
       # print("find",ret[1]['a']['n']) # obtem o nome pesquisa, se tiver.
        for item_id, item_infos in files.items():
            if 'n' in item_infos['a']:
                nome_arquivo = item_infos['a']['n']
                id_pasta = item_infos['p']
                if id_pasta == mega_folder_id_str and nome_arquivo == json_file:
                    return True        
    except Exception as e:
        logging.exception(f"existe_no_mega() - Erro ao verificar a existência do arquivo no Mega.nz: {e}")
        return False

def datetime_serialization(obj):
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def run_backup():
    global HASHES_ANTERIORES
            # Carregar os hashes anteriores se existirem
    if os.path.exists('hashes.json'):
        try:
            with open('hashes.json', 'r') as file:
                data = file.read()
                if data:
                    HASHES_ANTERIORES = json.loads(data)
        except Exception as e:
            logging.exception(f"run_backup() - Erro ao carregar os hashes anteriores: {e}")
            HASHES_ANTERIORES = {}

  #Agendar a verificação de backup para 00:00 horas todos os dias
  
    schedule.every().day.at('03:30').do(fazer_backup_arquivos)
    

    # Loop para executar as tarefas agendadas
    while True:
        schedule.run_pending()
        time.sleep(1)

   #     # Salvar os hashes atualizados em cada execução
        with open('hashes.json', 'w') as file:
           json.dump(HASHES_ANTERIORES, file, default=datetime_serialization)

# ============================================================================================================
#                            FIM PARTE DE BACKUP DIARIO 
# ============================================================================================================

def main():
    # Cria o atualizador e o bot
    updater = Updater(TOKEN_BOT, use_context=True)
  
    # Verifica se a pasta "Cadastros" existe, caso contrário, cria a pasta
    if not os.path.exists("Cadastros"):
        os.makedirs("Cadastros")
    # Obtém o despachante do bot
    dp = updater.dispatcher

    # Adiciona o logger ao objeto dispatcher para que as mensagens de log sejam gravadas no arquivo
    dp.logger.addHandler(file_handler)

    conversation_handlers = ConversationHandler(
        entry_points=[CommandHandler('calcular_multa', calcular_multa_start)],
        states={
            OBTER_VALOR_ALUGUEL: [MessageHandler(Filters.text & ~Filters.command, obter_valor_aluguel)],
            OBTER_VALOR_PAGO: [MessageHandler(Filters.text & ~Filters.command, obter_valor_pago)],
            OBTER_DATA_VENCIMENTO: [MessageHandler(Filters.text & ~Filters.command, obter_data_vencimento)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_operacao)],
    )
    dp.add_handler(conversation_handlers)

    # Criação do ConversationHandler para a conversação de envio de mensagem
    envio_mensagem_conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('mensagem', mensagem)],
        states={
            DIGITE_MENSAGEM: [MessageHandler(Filters.text & ~Filters.command, receber_mensagem)]
        },
        fallbacks=[CommandHandler('cancelar', cancelar_operacao)]
    )

    # Adição do ConversationHandler ao bot de controle
    dp.add_handler(envio_mensagem_conversation_handler)


    conversa_cadastro_despesa = ConversationHandler(
        entry_points=[CommandHandler('cadastrar_divida', iniciar_cadastro_despesa)],
            states={
                CATEGORIA: [MessageHandler(Filters.text, receber_categoria_despesa)],
                DATA_INICIO: [MessageHandler(Filters.text, receber_data_inicio_despesa)],
                DATA_PRIMEIRA_PARCELA: [MessageHandler(Filters.text, receber_data_primeira_parcela)],
                VALOR_TOTAL: [MessageHandler(Filters.text, receber_valor_total_despesa)],
                QUANTIDADE_PARCELAS: [MessageHandler(Filters.text, receber_quantidade_parcelas)],
                CARTAO_CREDITO: [MessageHandler(Filters.text, receber_cartao_credito)],
                CONFIRMAR_CADASTRO: [MessageHandler(Filters.text, confirmar_cadastro_despesa)],
                EDITAR_ITEM: [MessageHandler(Filters.text, editar_item_cadastro)],
                CONFIRMAR_EDICAO: [MessageHandler(Filters.text, confirmar_edicao_cadastro)],
                RECEBER_NOVO_VALOR: [MessageHandler(Filters.text, receber_novo_valor)]
            },
        fallbacks=[CommandHandler('cancelar', finalizar_cadastro_despesa)],
    )

    pagar_parcela_handler = ConversationHandler(
        entry_points=[CommandHandler('pagar_divida', escolher_parcela)],
        states={
            SELECTING_PARCELA: [MessageHandler(Filters.text & ~Filters.command, pagar_parcela)]
        },
        fallbacks=[CommandHandler('cancelar', cancelar_operacao)]
    )


    dp.add_handler(CommandHandler("multiplos_cadastros", criar_planilha))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("importar_planilha", importar_planilha)],
        states={
            UPLOADING: [
                MessageHandler(Filters.document, process_spreadsheet),
                CommandHandler("cancelar", cancelar_importacao),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_importacao)],
    )

    conversa_apagar_cadastro = ConversationHandler(
        entry_points=[CommandHandler("apagar_cadastro", apagar_cadastro)],
        states={
            RECEBENDO_ESCOLHA_DIVIDA_A_EXCLUIR: [MessageHandler(Filters.text, receber_escolha_divida_a_excluir)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_operacao)],
    )


    dp.add_handler(conv_handler)
    dp.add_handler(pagar_parcela_handler)
    dp.add_handler(conversa_cadastro_despesa)
    dp.add_handler(conversa_apagar_cadastro)
    dp.add_handler(CommandHandler("relatorio_excel", exibir_relatorio))
    dp.add_handler(CommandHandler("relatorio", relatorio_resumido))
    dp.add_handler(CommandHandler("bam", bam_audio, allow_edited=True))
    dp.add_handler(CommandHandler(["start", "help"], start_help))
    
    
    
    # Inicia o bot
    updater.start_polling()

    # Mantém o bot em execução até que Ctrl + C seja pressionado
    updater.idle()


# Executa o bot
if __name__ == '__main__':
    # Inicia a verificação de backup em uma thread
    backup_thread = threading.Thread(target=run_backup)
    backup_thread.daemon = True
    backup_thread.start()

    # Executa o bot do Telegram no thread principal
    main()


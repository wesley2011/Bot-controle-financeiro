
import os
import subprocess
from datetime import datetime
import schedule
import time
from telegram import Bot
from telegram.ext import Updater, CommandHandler
import configparser

# Token do bot de controle
TOKEN_CONTROLE = 'TOKEN BOT'

# ID do chat para enviar as notificações
CHAT_ID_NOTIFICACAO = 8238283822


# Diretório do bot principal
DIRETORIO_BOT_PRINCIPAL = ''

# Nome do arquivo do bot principal
NOME_ARQUIVO_BOT_PRINCIPAL = 'Bot_digi_'

# Arquivo de configuração
ARQUIVO_CONFIGURACAO = 'config.ini'

# Função para enviar uma mensagem de notificação
def enviar_notificacao_mensagem(texto):
    bot = Bot(token=TOKEN_CONTROLE)
    bot.send_message(chat_id=CHAT_ID_NOTIFICACAO, text=texto)

# Função para verificar o status do bot principal
def verificar_status_bot_principal():
    processo = subprocess.Popen(COMANDO_VERIFICAR_STATUS, shell=True, stdout=subprocess.PIPE)
    processo.wait()

    if processo.returncode == 0:
        print(f'{datetime.now()}: Bot principal está online.')
    else:
        print(f'{datetime.now()}: Bot principal está offline.')
        enviar_notificacao_mensagem(f'O bot principal ficou offline às {datetime.now()}')

# Função para agendar a verificação de status
def agendar_verificacao_status():
    schedule.every(1).minutes.do(verificar_status_bot_principal)

# Configuração da verificação de status
agendar_verificacao_status()

# Handler para o comando /start
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text='Bot de controle iniciado.')

# Handler para o comando /status
def status(update, context):
    processo = subprocess.Popen(COMANDO_VERIFICAR_STATUS, shell=True, stdout=subprocess.PIPE)
    processo.wait()

    if processo.returncode == 0:
        status_msg = 'Bot principal está online.'
    else:
        status_msg = 'Bot principal está offline.'

    context.bot.send_message(chat_id=update.effective_chat.id, text=status_msg)

# Handler para o comando /restart
def restart(update, context):
    if os.path.exists(NOME_ARQUIVO_BOT_PRINCIPAL):
        os.remove(NOME_ARQUIVO_BOT_PRINCIPAL)
        # Verificar se o arquivo de configuração existe
        if os.path.isfile(ARQUIVO_CONFIGURACAO):
            # Carregar os parâmetros de configuração
            config = configparser.ConfigParser()
            config.read(ARQUIVO_CONFIGURACAO)

            link_bot_principal = config['BOT_PRINCIPAL']['link']
            permissao_execucao = config['BOT_PRINCIPAL']['permissao_execucao']

    else:
        config = configparser.ConfigParser()
        config.read(ARQUIVO_CONFIGURACAO)

        link_bot_principal = config['BOT_PRINCIPAL']['link']
        permissao_execucao = config['BOT_PRINCIPAL']['permissao_execucao']

    instalar_e_iniciar_bot_controle(link_bot_principal, permissao_execucao)

# Handler para o comando /stop
def stop(update, context):
    subprocess.call(f'pkill -f {NOME_ARQUIVO_BOT_PRINCIPAL}', shell=True)
    context.bot.send_message(chat_id=update.effective_chat.id, text='Bot principal desligado.')

# Handler para o comando /log
def log(update, context):
    log_file = os.path.join(DIRETORIO_BOT_PRINCIPAL, 'bot.log')

    if os.path.isfile(log_file):
        context.bot.send_document(chat_id=update.effective_chat.id, document=open(log_file, 'rb'))
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text='Arquivo de log não encontrado.')


# Criação do bot de controle
bot_controle = Bot(token=TOKEN_CONTROLE)
updater = Updater(bot=bot_controle, use_context=True)

# Adição dos handlers dos comandos
updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(CommandHandler('status', status))
updater.dispatcher.add_handler(CommandHandler('restart', restart))
updater.dispatcher.add_handler(CommandHandler('stop', stop))
updater.dispatcher.add_handler(CommandHandler('log', log))

# Função para iniciar o bot de controle
def iniciar_bot_controle():
    updater.start_polling()
    print('Bot de controle iniciado.')

# Função para parar o bot de controle
def parar_bot_controle():
    updater.stop()
    print('Bot de controle parado.')

# Função para instalar e iniciar o bot de controle
def instalar_e_iniciar_bot_controle(link_bot_principal, permissao_execucao):
    # Salvar os parâmetros de configuração
    config = configparser.ConfigParser()
    config['BOT_PRINCIPAL'] = {
        'link': link_bot_principal,
        'permissao_execucao': permissao_execucao
    }
    with open(ARQUIVO_CONFIGURACAO, 'w') as config_file:
        config.write(config_file)

    # Baixar o código do bot principal
    subprocess.call(f'wget {link_bot_principal} -O {NOME_ARQUIVO_BOT_PRINCIPAL} 1>/dev/null 2>/dev/null', shell=True)

    # Dar permissão de execução para o arquivo do bot principal
    subprocess.call(f'chmod {permissao_execucao} {NOME_ARQUIVO_BOT_PRINCIPAL}', shell=True)



    # Definir o diretório do bot principal
    global DIRETORIO_BOT_PRINCIPAL
    DIRETORIO_BOT_PRINCIPAL = os.path.dirname(os.path.abspath(NOME_ARQUIVO_BOT_PRINCIPAL))

    # Definir o comando para verificar o status do bot principal
    global COMANDO_VERIFICAR_STATUS
    COMANDO_VERIFICAR_STATUS = f'pgrep -f {NOME_ARQUIVO_BOT_PRINCIPAL}'
    processo = subprocess.Popen(COMANDO_VERIFICAR_STATUS, shell=True, stdout=subprocess.PIPE)
    processo.wait()

    if processo.returncode == 0:
        print('bbb Bot principal está online.')
    else:
        subprocess.call(f'python3 {NOME_ARQUIVO_BOT_PRINCIPAL} &', shell=True)
    
    print("Bot principal iniciado.\n")

    # Iniciar o bot de controle
    iniciar_bot_controle()

if __name__ == '__main__':
    print('Seja bem-vindo ao Bot de Controle!')
    print('Por favor, insira as informações abaixo para iniciar o bot de controle:')

    # Verificar se o arquivo de configuração existe
    if os.path.isfile(ARQUIVO_CONFIGURACAO):
        # Carregar os parâmetros de configuração
        config = configparser.ConfigParser()
        config.read(ARQUIVO_CONFIGURACAO)

        link_bot_principal = config['BOT_PRINCIPAL']['link']
        permissao_execucao = config['BOT_PRINCIPAL']['permissao_execucao']
    else:
        # Solicitar o link do bot principal
        link_bot_principal = input('Link do código do bot principal: ')

        # Solicitar permissões de execução para o arquivo do bot principal
        permissao_execucao = input('Permissão de execução para o arquivo do bot principal (ex: 755): ')


    coded = subprocess.call(f'pgrep -f {NOME_ARQUIVO_BOT_PRINCIPAL}', shell=True)


    if coded > 0:
        print('Bot principal está online.')
    else:
        # Instalar e iniciar o bot de controle
        instalar_e_iniciar_bot_controle(link_bot_principal, permissao_execucao)


import multiprocessing
import os

# Porta onde o servidor vai correr (O Render define a porta automaticamente)
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"

# Número de processos (Workers)
# Uma fórmula comum é (2 x número de cores) + 1
# No plano gratuito do Render, 2 ou 3 workers são ideais para não estourar a RAM
workers = 2

# Tipo de worker - 'sync' é o padrão, 'gthread' é bom para I/O (leitura de ficheiros/DB)
worker_class = 'gthread'
threads = 4

# Tempo máximo que um processo pode demorar a responder (em segundos)
# Como o processamento de Excel pode ser lento, aumentamos para 120s
timeout = 120

# Nível de log (info, debug, error, warning)
loglevel = 'info'
accesslog = "-"  # Envia logs de acesso para a consola do Render
errorlog = "-"   # Envia logs de erro para a consola do Render

# Preload da aplicação para poupar memória RAM
preload_app = True
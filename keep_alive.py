import os # <-- ¡Asegúrate de incluir 'os' aquí!
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Hola, estoy vivo!"

# Función que inicia el servidor de Flask
def run():
    # Render usa la variable de entorno PORT (que es 10000)
    port = int(os.environ.get("PORT", 10000)) 
    app.run(host='0.0.0.0', port=port)

def keep_alive(): # <-- ¡ESTA FUNCIÓN FALTABA!
    t = Thread(target=run)
    t.start()
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ El bot está corriendo en modo automático y monetizando..."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

from flask import Flask, request, jsonify
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import smtplib
from email.mime.text import MIMEText
import os
from io import TextIOWrapper

app = Flask(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = "ton.mail@gmail.com"
EMAIL_PASS = "ton_mdp"

env = Environment(loader=FileSystemLoader("templates"))

def charger_template(langue):
    return env.get_template(f"{langue}_email.txt")

def envoyer_mail(to_email, sujet, corps):
    msg = MIMEText(corps, "plain", "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = sujet

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

@app.route("/send", methods=["POST"])
def send_mails():
    csv_file = request.files['file']
    stage = request.form['stage']

    if stage not in ["Chhaju", "Anu"]:
        return jsonify({"error": "Nom de stage invalide"}), 400

    df = pd.read_csv(TextIOWrapper(csv_file, encoding='utf-8'))
    df = df.rename(columns={
        "First name": "prenom",
        "Last Name": "nom",
        "Email": "email",
        "Stage": "stage",
        "Country, nationality": "pays"
    })

    df_filtre = df[df["stage"] == stage]
    total = 0

    for _, row in df_filtre.iterrows():
        langue = "fr" if row["pays"].strip().lower() in ["france", "cameroun", "côte d'ivoire", "bénin", "togo"] else "en"
        genre = "f" if row["prenom"][-1].lower() in ["a", "e"] else "m"

        template = charger_template(langue)
        contenu = template.render(prenom=row["prenom"], nom=row["nom"], genre=genre, stage=stage)
        lines = contenu.strip().splitlines()
        sujet = lines[0].replace("Subject:", "").replace("Objet:", "").strip()
        corps = "\n".join(lines[1:]).strip()

        envoyer_mail(row["email"], sujet, corps)
        total += 1

    return jsonify({"envoyes": total})

if __name__ == "__main__":
    app.run(debug=True)

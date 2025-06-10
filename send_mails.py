from flask import Flask, request, jsonify
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import smtplib
from email.mime.text import MIMEText
import os
from io import TextIOWrapper
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))

# Email configurations for different stages
EMAIL_CONFIGS = {
    "stage1": {
        "name": os.getenv("STAGE1_NAME"),
        "email": os.getenv("STAGE1_EMAIL"),
        "password": os.getenv("STAGE1_PASSWORD")
    },
    "stage2": {
        "name": os.getenv("STAGE2_NAME"),
        "email": os.getenv("STAGE2_EMAIL"),
        "password": os.getenv("STAGE2_PASSWORD")
    }
}

env = Environment(loader=FileSystemLoader("templates"))

def charger_template(langue):
    return env.get_template(f"{langue}_email.txt")

def envoyer_mail(to_email, sujet, corps, stage_config):
    msg = MIMEText(corps, "plain", "utf-8")
    msg["From"] = stage_config["email"]
    msg["To"] = to_email
    msg["Subject"] = sujet

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(stage_config["email"], stage_config["password"])
        server.send_message(msg)

def get_stage_config(stage_name):
    """Get the email configuration for a given stage name."""
    for config in EMAIL_CONFIGS.values():
        if config["name"] == stage_name:
            return config
    return None

@app.route("/send", methods=["POST"])
def send_mails():
    csv_file = request.files['file']
    stage = request.form['stage']

    # Read and process the CSV file
    df = pd.read_csv(TextIOWrapper(csv_file, encoding='utf-8'))
    df = df.rename(columns={
        "First name": "prenom",
        "Last Name": "nom",
        "Email": "email",
        "Stage": "stage",
        "Country, nationality": "pays"
    })

    # Get unique stages from the CSV
    available_stages = df["stage"].unique()
    
    # Validate if the provided stage exists in the CSV
    if stage not in available_stages:
        return jsonify({
            "error": "Stage invalide",
            "available_stages": list(available_stages)
        }), 400

    # Get the email configuration for the given stage name
    stage_config = get_stage_config(stage)
    
    if not stage_config:
        return jsonify({
            "error": f"Configuration email manquante pour le stage '{stage}'"
        }), 500

    if not stage_config["email"] or not stage_config["password"]:
        return jsonify({
            "error": f"Configuration email incomplète pour le stage '{stage}'"
        }), 500

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

        envoyer_mail(row["email"], sujet, corps, stage_config)
        total += 1

    return jsonify({
        "envoyes": total,
        "stage": stage
    })

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


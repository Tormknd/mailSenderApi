from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import smtplib
from email.mime.text import MIMEText
import os
from io import TextIOWrapper
from dotenv import load_dotenv
import csv
import io
import csv as pycsv
import sys
from langdetect import detect
import unicodedata


# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

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

def normalize_text(text):
    # Lowercase, remove accents, and strip punctuation for robust matching
    text = text.lower().strip()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

TEMPLATE_MAP = [
    # (normalized comment, template filename)
    (normalize_text("Pouvez vous m'envoyer des informations supplémentaires sur ce programme ?"), "fr_informations_email.txt"),
    (normalize_text("Can you send me more information about this program?"), "en_informations_email.txt"),
    (normalize_text("When is the application deadline for this program?"), "en_deadline_email.txt"),
    (normalize_text("Quelle est la date limite d'inscription à ce programme ?"), "fr_deadline_email.txt"),
    (normalize_text("What documents are required to apply to this program?"), "en_apply_email.txt"),
]

def get_template_filename(comment, langue):
    norm_comment = normalize_text(comment)
    for key, filename in TEMPLATE_MAP:
        if key in norm_comment:
            return filename
    # fallback to default
    return f"{langue}_informations_email.txt"

def charger_template(langue):
    return env.get_template(f"{langue}_email.txt")

def envoyer_mail(to_email, sujet, corps, stage_config):
    msg = MIMEText(corps, "plain", "utf-8")
    msg["From"] = stage_config["email"]
    msg["To"] = to_email
    msg["Subject"] = sujet

    print(f"[LOG] Preparing to send email to: {to_email} | Subject: {sujet} | From: {stage_config['email']}")

    if SMTP_PORT == 465:
        # Use SSL for port 465
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(stage_config["email"], stage_config["password"])
            server.send_message(msg)
    else:
        # Use STARTTLS for other ports (e.g., 587)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(stage_config["email"], stage_config["password"])
            server.send_message(msg)

def get_stage_config(stage_name):
    for config in EMAIL_CONFIGS.values():
        if config["name"] == stage_name:
            return config
    return None

@app.route("/send", methods=["POST"])
def send_mails():
    csv_file = request.files['file']
    stage = request.form['stage']
    file_content = csv_file.read()

    # Debug: print first 500 characters of uploaded file
    print('DEBUG: First 500 chars of uploaded file:', file_content[:500])

    # Read the uploaded Excel file
    df = pd.read_excel(csv_file)
    print('DEBUG: Columns in Excel:', df.columns.tolist())
    print('DEBUG: First few rows:', df.head())
    # Normalize columns for case-insensitive matching and strip quotes
    df.columns = df.columns.str.strip().str.lower().str.replace('"', '')
    needed_cols = ["first name", "last name", "email", "stage", "country, nationality", "comment"]
    missing_cols = [col for col in needed_cols if col not in df.columns]
    if missing_cols:
        print(f'ERROR: Missing columns in Excel: {missing_cols}')
        return jsonify({"error": f"Colonnes manquantes dans le fichier Excel: {missing_cols}"}), 400
    # Keep only needed columns and rename for your code
    df = df[needed_cols]
    df = df.rename(columns={
        "first name": "prenom",
        "last name": "nom",
        "email": "email",
        "stage": "stage",
        "country, nationality": "pays",
        "comment": "comment"
    })

    df["stage"] = df["stage"].astype(str).str.replace('"', '').str.strip()
    stage = stage.strip()

    print("STAGE reçu dans la requête :", stage, file=sys.stdout, flush=True)
    print("STAGES trouvés dans le CSV :", df["stage"].unique(), file=sys.stdout, flush=True)

    available_stages = df["stage"].unique()
    if stage not in available_stages:
        return jsonify({
            "error": "Stage invalide",
            "available_stages": list(available_stages)
        }), 400

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

    # Find the actual comment column name (case-insensitive)
    comment_col = next((col for col in df_filtre.columns if col.lower() == "comment"), None)
    # Find the actual program column name (case-insensitive)
    program_col = next((col for col in df_filtre.columns if col.lower() == "program"), None)
    unmatched_students = []
    sent_count = 0
    for _, row in df_filtre.iterrows():
        comment = row[comment_col] if comment_col else ""
        program = row[program_col] if program_col else ""
        print(f"[DEBUG] Comment for language detection: {comment}")
        try:
            lang = detect(comment)
        except:
            lang = "en"  # fallback if detection fails
        if lang == "fr":
            langue = "fr"
        else:
            langue = "en"
        genre = "f" if row["prenom"][-1].lower() in ["a", "e"] else "m"

        # Only send if the comment matches exactly a TEMPLATE_MAP entry
        norm_comment = normalize_text(comment)
        matched_template = None
        for key, filename in TEMPLATE_MAP:
            if key == norm_comment:
                matched_template = filename
                break
        if not matched_template:
            unmatched_students.append({
                "prenom": row["prenom"],
                "nom": row["nom"],
                "email": row["email"],
                "comment": comment,
                "program": program
            })
            continue  # skip sending
        print(f"[DEBUG] Using template: {matched_template}")
        template = env.get_template(matched_template)
        contenu = template.render(prenom=row["prenom"], nom=row["nom"], genre=genre, stage=stage)
        lines = contenu.strip().splitlines()
        sujet = lines[0].replace("Subject:", "").replace("Objet:", "").strip()
        corps = "\n".join(lines[1:]).strip()

        print(f"[LOG] Preparing to send email to: {row['email']} | Subject: {sujet} | From: {stage_config['email']} | Language: {langue} | Template: {matched_template} | Comment: {comment}")

        envoyer_mail(row["email"], sujet, corps, stage_config)
        sent_count += 1

    return jsonify({
        "envoyes": sent_count,
        "stage": stage,
        "unmatched": unmatched_students
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

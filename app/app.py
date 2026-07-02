"""
Kids Storytelling App - local Flask frontend server.

This Flask app only serves HTML/CSS/JS pages. All real business logic
(auth, story upload, story listing, notifications) happens in AWS Lambda
behind API Gateway - the browser JS talks to that API directly.

Run: python app.py   (from inside the app/ directory)
Then open http://127.0.0.1:5000
"""

import json
import os

from flask import Flask, render_template, jsonify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_FILE = os.path.join(ROOT, "aws_resources.json")

app = Flask(__name__)


def load_api_endpoint():
    if not os.path.exists(RESOURCES_FILE):
        return None
    with open(RESOURCES_FILE) as f:
        data = json.load(f)
    return data.get("api_endpoint")


@app.context_processor
def inject_api_endpoint():
    return {"api_endpoint": load_api_endpoint() or ""}


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login/<role>")
def login(role):
    if role not in ("teacher", "student"):
        role = "student"
    return render_template("login.html", role=role)


@app.route("/signup/<role>")
def signup(role):
    if role not in ("teacher", "student"):
        role = "student"
    return render_template("signup.html", role=role)


@app.route("/teacher/dashboard")
def teacher_dashboard():
    return render_template("teacher_dashboard.html")


@app.route("/student/dashboard")
def student_dashboard():
    return render_template("student_dashboard.html")


@app.route("/api/config")
def config():
    endpoint = load_api_endpoint()
    if not endpoint:
        return jsonify({"error": "AWS resources not provisioned yet. Run setup/provision_aws.py first."}), 500
    return jsonify({"api_endpoint": endpoint})


if __name__ == "__main__":
    if not os.path.exists(RESOURCES_FILE):
        print("=" * 70)
        print("WARNING: aws_resources.json not found.")
        print("Run 'python setup/provision_aws.py' from the project root first.")
        print("=" * 70)
    app.run(debug=True, port=5000)

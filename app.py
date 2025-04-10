from flask import Flask, render_template, redirect, url_for, request
from project import app
from waitress import serve

app = Flask(__name__,)

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000, threads=8)
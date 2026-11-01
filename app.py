"""Flightbook's server-rendered web application."""

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index():
    """Show the public flight diary homepage."""
    return render_template("index.html")

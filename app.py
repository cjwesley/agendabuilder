from flask import Flask, render_template

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("snapshot.html.j2")


if __name__ == "__main__":
    app.run(debug=True)

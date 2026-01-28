from flask import Flask, render_template

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static"
)

@app.get("/")
def index():
    # nanti angka-angka ini diambil dari hasil proses kalian
    stats = {
        "total_raw": 0,
        "total_processed": 0,
        "vocab_size": 0,
        "prob": {"positif": 0, "negatif": 0, "netral": 0},
    }
    return render_template("dashboard.html", stats=stats)

if __name__ == "__main__":
    app.run(debug=True)

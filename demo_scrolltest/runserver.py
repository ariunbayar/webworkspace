from livereload import Server
from flask import Flask, render_template


app = Flask(__name__)
app.debug = True


@app.route("/")
def index():
    return render_template('index.html', name='john')


if __name__ == "__main__":
    if app.debug == False:
        app.run(port=8000)
    else:
        server = Server(app.wsgi_app)
        server.watch('static')
        server.watch('templates')
        server.serve(port=8000)

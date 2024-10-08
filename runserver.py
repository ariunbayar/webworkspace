import json

import redis
from livereload import Server

from flask import Flask
from flask import render_template, jsonify, send_file
from flask import request

from thumbnail import generate_thumbnail


app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.debug = True

cache = redis.StrictRedis(host='127.0.0.1', port=6379, db=2, charset="utf-8", decode_responses=True)


@app.route("/")
def index():
    return render_template('index.html', name='john')


@app.route("/files")
def files():
    file_ids = json.loads(cache.get('file_ids'))
    files = []
    for file_id in file_ids:
        file_item = json.loads(cache.get('file_%s' % file_id))
        files.append(file_item)

    rval = files

    return jsonify(rval)


@app.route("/file/<int:file_id>", methods=['PUT', 'POST', 'PATCH'])
def file_save(file_id):
    # TODO GET
    file_item = json.loads(cache.get('file_%s' % file_id))

    values = request.get_json()
    file_item.update(values)

    cache.set('file_%s' % file_id, json.dumps(file_item))
    file_item['top'] = file_item['left']

    return jsonify({'success': True})


@app.route("/file/<int:file_id>", methods=['DELETE'])
def file_delete(file_id):
    cache.delete('file_%s' % file_id)

    return jsonify({'success': True})


@app.route("/thumbnail/<int:file_id>")
def thumbnail(file_id):
    file_item = json.loads(cache.get('file_%s' % file_id))
    proj_dir = json.loads(cache.get('project_38'))['directory']
    img = generate_thumbnail(proj_dir + file_item['filename'])

    return send_file(img, mimetype='image/png')


if __name__ == "__main__":
    if app.debug == False:
        app.run(port=8000)
    else:
        server = Server(app.wsgi_app)
        server.watch('static')
        server.watch('static/js')
        server.watch('templates')
        server.serve(port=8000)

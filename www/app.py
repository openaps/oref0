import os
import socket

from flask import Flask, render_template, url_for, json, jsonify
app = Flask(__name__)

@app.route("/")
def index():
    try:
      myopenaps_dir = os.environ['OPENAPS_DIR']
    except KeyError:
        myopenaps_dir = "/root/myopenaps/"
    data=dict()
    try:
        data['hostname']=socket.gethostname()
        glucose = json.load(open(os.path.join(myopenaps_dir, "monitor/glucose.json")))
        data['glucose']=glucose[0]
        # TODO: calculate delta properly when glucose[1] isn't 5m ago
        delta=glucose[0]['glucose']-glucose[1]['glucose']
        tick=""
        if delta >= 0:
            tick += "+"
        tick += str(delta)
        data['tick']=tick
        iob = json.load(open(os.path.join(myopenaps_dir, "monitor/iob.json")))
        data['iob'] = iob[0]
        data['meal'] = json.load(open(os.path.join(myopenaps_dir, "monitor/meal.json")))
        data['suggested'] = json.load(open(os.path.join(myopenaps_dir, "enact/suggested.json")))
        data['enacted'] = json.load(open(os.path.join(myopenaps_dir, "enact/enacted.json")))
        data['temp_basal'] = json.load(open(os.path.join(myopenaps_dir, "monitor/temp_basal.json")))
        # print(data)
    except ValueError:
       return render_template('indexError.html', data=data )
    else:        
       return render_template('index.html', data=data )

@app.route("/enacted")
def enacted():
    #SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
    json_url = os.path.join("/root/myopenaps/enact/enacted.json")
    data = json.load(open(json_url))
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

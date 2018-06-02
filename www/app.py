import os
import socket

from flask import Flask, render_template, url_for, json, jsonify, request
from datetime import datetime
import pytz

app = Flask(__name__)

@app.route("/")
def index():
    try:
      myopenaps_dir = os.environ['OPENAPS_DIR']
    except KeyError:
        myopenaps_dir = "/root/myopenaps/"
    data=dict()
    try:
        error_text = "getHost"
        data['hostname']=socket.gethostname()
        error_text = "pump_loop_success"
        if os.path.isfile("/tmp/pump_loop_success"):
            data['loop_completed']=datetime.fromtimestamp(os.path.getmtime("/tmp/pump_loop_success"), pytz.utc)
        else:
            data['loop_completed']=""
            
    except ValueError:
        return render_template('indexError.html', data=data, error_text=error_text )
    except IOError:
        return render_template('indexError.html', data=data, error_text=error_text )
    else:
        return render_template('index.html', data=data )

@app.route("/suggested")
def suggested():
    json_url = os.path.join("/root/myopenaps/enact/suggested.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/enacted")
def enacted():
    json_url = os.path.join("/root/myopenaps/enact/enacted.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/glucose")
def glucose():
    if os.path.getmtime("/root/myopenaps/xdrip/glucose.json") > os.path.getmtime("/root/myopenaps/monitor/glucose.json"):
        json_url = os.path.join("/root/myopenaps/xdrip/glucose.json")
    else:
        json_url = os.path.join("/root/myopenaps/monitor/glucose.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/sgv.json")
def sgvjson():
    json_url = os.path.join("/root/myopenaps/settings/profile.json")
    data = json.load(open(json_url))
    units = data['out_units']
    count = request.args.get('count', default = 10, type = int)
    if os.path.getmtime("/root/myopenaps/xdrip/glucose.json") > os.path.getmtime("/root/myopenaps/monitor/glucose.json"):
        json_url = os.path.join("/root/myopenaps/xdrip/glucose.json")
    else:
        json_url = os.path.join("/root/myopenaps/monitor/glucose.json")
    data = json.load(open(json_url))
    if units == "mg/dL":
        data[0]['units_hint'] = "mgdl"
    else:
        data[0]['units_hint'] = "mmol"
    return jsonify(data[0:count])

@app.route("/temptargets")
def temptargets():
    json_url = os.path.join("/root/myopenaps/settings/temptargets.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/profile")
def profile():
    json_url = os.path.join("/root/myopenaps/settings/profile.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/pumphistory")
def pumphistory():
    json_url = os.path.join("/root/myopenaps/monitor/pumphistory-24h-zoned.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/iob")
def iob():
    json_url = os.path.join("/root/myopenaps/monitor/iob.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/pump_battery")
def pump_battery():
    json_url = os.path.join("/root/myopenaps/monitor/battery.json")
    data = json.load(open(json_url))
    return jsonify(data)
    
@app.route("/edison_battery")
def edison_battery():
    json_url = os.path.join("/root/myopenaps/monitor/edison-battery.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/meal")
def meal():
    json_url = os.path.join("/root/myopenaps/monitor/meal.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/temp_basal")
def temp_basal():
    json_url = os.path.join("/root/myopenaps/monitor/temp_basal.json")
    data = json.load(open(json_url))
    return jsonify(data)
    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

import os
import socket

from flask import Flask, render_template, url_for, json, jsonify, request
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)
myopenaps_dir = "/root/myopenaps/"
    
def getip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

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
    json_url = os.path.join(myopenaps_dir + "enact/suggested.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/enacted")
def enacted():
    json_url = os.path.join(myopenaps_dir + "enact/enacted.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/glucose")
def glucose():
    if os.path.getmtime(myopenaps_dir + "xdrip/glucose.json") > os.path.getmtime(myopenaps_dir + "monitor/glucose.json") and os.path.getsize(myopenaps_dir + "xdrip/glucose.json") > 0:
        json_url = os.path.join(myopenaps_dir + "xdrip/glucose.json")
    else:
        json_url = os.path.join(myopenaps_dir + "monitor/glucose.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/sgv.json")
def sgvjson():
    json_url = os.path.join(myopenaps_dir + "settings/profile.json")
    data = json.load(open(json_url))
    units = data['out_units']
    count = request.args.get('count', default = 10, type = int)
    if os.path.getmtime(myopenaps_dir + "xdrip/glucose.json") > os.path.getmtime(myopenaps_dir + "monitor/glucose.json"):
        json_url = os.path.join(myopenaps_dir + "xdrip/glucose.json")
    else:
        json_url = os.path.join(myopenaps_dir + "monitor/glucose.json")
    data = json.load(open(json_url))
    if units == "mg/dL":
        data[0]['units_hint'] = "mgdl"
    else:
        data[0]['units_hint'] = "mmol"
    return jsonify(data[0:count])

@app.route("/temptargets")
def temptargets():
    json_url = os.path.join(myopenaps_dir + "settings/temptargets.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/cgm")
def cgm():
    json_url = os.path.join(myopenaps_dir + "monitor/xdripjs/cgm-pill.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/system")
def system():
    data = {}
    data['hostname'] = socket.gethostname() 
    data['ip'] = getip() 
    return jsonify(data) 


@app.route("/profile")
def profile():
    json_url = os.path.join(myopenaps_dir + "settings/profile.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/pumphistory")
def pumphistory():
    json_url = os.path.join(myopenaps_dir + "monitor/pumphistory-24h-zoned.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/iob")
def iob():
    json_url = os.path.join(myopenaps_dir + "monitor/iob.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/pump_battery")
def pump_battery():
    json_url = os.path.join(myopenaps_dir + "monitor/battery.json")
    data = json.load(open(json_url))
    return jsonify(data)
    
@app.route("/edison_battery")
def edison_battery():
    json_url = os.path.join(myopenaps_dir + "monitor/edison-battery.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/meal")
def meal():
    json_url = os.path.join(myopenaps_dir + "monitor/meal.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/temp_basal")
def temp_basal():
    json_url = os.path.join(myopenaps_dir + "monitor/temp_basal.json")
    data = json.load(open(json_url))
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

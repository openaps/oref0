import os
import socket

from flask import Flask, render_template, url_for, json, jsonify
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
            
        error_text = "battery"
        data['battery'] = json.load(open(os.path.join(myopenaps_dir, "monitor/battery.json")))
        
        error_text = "edison"
        data['edison_battery'] = json.load(open(os.path.join(myopenaps_dir, "monitor/edison-battery.json")))
        
        error_text = "meal"
        data['meal'] = json.load(open(os.path.join(myopenaps_dir, "monitor/meal.json")))

        error_text = "suggested"
        data['suggested'] = json.load(open(os.path.join(myopenaps_dir, "enact/suggested.json")))

        error_text = "temp_basal"
        data['temp_basal'] = json.load(open(os.path.join(myopenaps_dir, "monitor/temp_basal.json")))
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
    if os.path.isfile("/root/myopenaps/xdrip/glucose.json"):
        json_url = os.path.join("/root/myopenaps/xdrip/glucose.json")
    else:
        json_url = os.path.join("/root/myopenaps/monitor/glucose.json")
    data = json.load(open(json_url))
    return jsonify(data)

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
    json_url = os.path.join("/root/myopenaps/monitor/pumphistory-merged.json")
    data = json.load(open(json_url))
    return jsonify(data)

@app.route("/iob")
def iob():
    json_url = os.path.join("/root/myopenaps/monitor/iob.json")
    data = json.load(open(json_url))
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

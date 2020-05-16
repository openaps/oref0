import os
import socket

from flask import Flask, render_template, url_for, json, jsonify, request
from flask_cors import CORS
from datetime import datetime
import pytz

import json
import subprocess
import re
from time import sleep
from functools import wraps

from dateutil import parser
from threading import Thread

import configparser


app = Flask(__name__)
CORS(app)

try:
    myopenaps_dir = os.environ['OPENAPS_DIR']
except KeyError:
    myopenaps_dir = "/root/myopenaps/"


config = configparser.ConfigParser()

config.read(os.path.join(myopenaps_dir + "ns.ini"))
config.read(os.path.join(myopenaps_dir + "pump.ini"))

NS_URL = config['device "ns"']['args'].split(' ')[1]
NS_TOKEN = config['device "ns"']['args'].split(' ')[2]
MEDTRONIC_PUMP_ID = config['device "pump"']['serial']
MEDTRONIC_FREQUENCY = None

AUTHORIZATION_ENABLED = json.load(open(os.path.join(myopenaps_dir + "flask_server.json")))["AUTHORIZATION_ENABLED"]


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

def check_authorization(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if AUTHORIZATION_ENABLED and request.headers.get("Authorization", None) != NS_TOKEN:
            return '', 401
        return f(*args, **kwargs)
    return wrapper

def read_medtronic_frequency():
    global MEDTRONIC_FREQUENCY
    try:
        mmtune_data = json.load(open(os.path.join(myopenaps_dir + "monitor/mmtune.json")))
        if mmtune_data["usedDefault"]:
            MEDTRONIC_FREQUENCY = "868.4" if config['device "pump"']['radio_locale'] == "WW" else "916.55"
        else:
            MEDTRONIC_FREQUENCY= str(mmtune_data["setFreq"])
    except IOError:
        MEDTRONIC_FREQUENCY = "868.4" if config['device "pump"']['radio_locale'] == "WW" else "916.55"

def read_oref_status():
    return json.load(open(os.path.join(myopenaps_dir + "oref0.json")))["OREF0_CAN_RUN"]

def switch_oref_status(oref_enabled):
    config_data = json.load(open(os.path.join(myopenaps_dir + "oref0.json")))

    config_data["OREF0_CAN_RUN"] = oref_enabled

    with open(os.path.join(myopenaps_dir + "oref0.json"), "w") as config_file:
        config_file.write(json.dumps(config_data, indent=2))

    if not oref_enabled:
        os.system("killall-g oref0-cron-every-minute")

def set_bolusing(new_status):
    try:
        status_json = json.load(open(os.path.join(myopenaps_dir + "monitor/status.json")))
        status_json["bolusing"] = new_status
        with open(os.path.join(myopenaps_dir + "monitor/status.json"), "w") as status_file:
            status_file.write(json.dumps(status_json, indent=2))
    except ValueError:
        pass


class Command:
    def __init__(self, cmd, timeout=15):
        self.cmd = cmd
        self.process = None
        self.timeout = timeout
        self.timeout_exit = False
        self.stdout = None
        self.stderr = None
        self.return_code = None

    def run(self):
        self.process = subprocess.Popen(" ".join(self.cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True,
                                        cwd=myopenaps_dir, env={"MEDTRONIC_PUMP_ID": MEDTRONIC_PUMP_ID, "MEDTRONIC_FREQUENCY": MEDTRONIC_FREQUENCY})

        for _ in range(self.timeout * 100):
            sleep(.01)
            if self.process.poll() is not None:
                self.return_code = self.process.returncode
                break
        else:
            self.timeout_exit = True
            self.process.kill()

        self.stdout, self.stderr = self.process.communicate()
    
    def execute(self, need_disable_oref=False):
        if self.cmd[0] == "mdt":
            read_medtronic_frequency()

        oref_enabled = read_oref_status()

        if oref_enabled and need_disable_oref:
            switch_oref_status(False)

        self.run()

        if oref_enable and need_disable_oref:
            switch_oref_status(True)

        if self.timeout_exit:
            return json.dumps({"result": {"stdout": "", "stderr": "TimeOutException"}, "is_error": True}), True
        
        return json.dumps({"result": {"stdout": self.stdout, "stderr": self.stderr}, "is_error": self.return_code != 0}), self.return_code != 0


@app.route("/")
def index():
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
    if os.path.exists(myopenaps_dir + "xdrip/glucose.json") and \
            os.path.getmtime(myopenaps_dir + "xdrip/glucose.json") > os.path.getmtime(myopenaps_dir + "monitor/glucose.json"):
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

@app.route("/pump_serial")
def get_serial():
    return json.dumps({"serial": MEDTRONIC_PUMP_ID})

@app.route("/reservoir")
def oref_reservoir():
    return open(os.path.join(myopenaps_dir + "monitor/reservoir.json")).read()

@app.route("/nightscout")
@check_authorization
def get_nightscout():
    return json.dumps({"url": NS_URL, "api_hash": NS_TOKEN})

@app.route("/carbs")
def oref_carbs():
    return open(os.path.join(myopenaps_dir + "settings/carbhistory.json")).read()


@app.route("/status")
def status():
    return open(os.path.join(myopenaps_dir + "monitor/status.json")).read()


@app.route("/settings")
def oref_settings():
    return open(os.path.join(myopenaps_dir + "settings/settings.json")).read()


@app.route("/clock")
def oref_clock():
    return open(os.path.join(myopenaps_dir + "monitor/clock-zoned.json")).read()


@app.route("/append_local_temptarget")
def oref_append_local_temptarget():
    try:
        target = int(float(request.args.get("target")))
        duration = int(request.args.get("duration"))
    except (KeyError, ValueError):
        return '', 400
    try:
        if request.args.get("start_time") != None:
            parser.parse(request.args.get("start_time"))
            start_time = request.args.get("start_time")
        else:
            start_time = None
    except (KeyError, ValueError):
        start_time = None

    args = ["oref0-append-local-temptarget", str(target), str(duration)]
    if start_time:
        args.append(start_time)
    return Command(args, 15).execute()[0]


@app.route("/preferences", methods=['GET', 'POST'])
@check_authorization
def preferences():
    if request.method == "GET":
        return open(os.path.join(myopenaps_dir + "preferences.json")).read()
    elif request.method == "POST":
        json_content = request.get_json(force=True)
        with open(os.path.join(myopenaps_dir + "preferences.json"), 'w') as preferences_file:
            preferences_file.write(json.dumps(json_content, indent=2))
        return '', 200


@app.route("/autotune_recommendations")
def autotune_recommendations():
    Command(['oref0-autotune-recommends-report', myopenaps_dir], 15).execute()
    return open(os.path.join(myopenaps_dir + "autotune/autotune_recommendations.log")).read()


@app.route("/enter_bolus")
@check_authorization
def enter_bolus():
    try:
        units = float(request.args.get("units"))
    except (KeyError, ValueError):
        return '', 400

    with open(os.path.join(myopenaps_dir + "enter_bolus.json"), 'w') as enter_bolus_file:
        enter_bolus_file.write("{ \"units\": %s }" % units)

    result, is_error = Command(["mdt", "bolus", "enter_bolus.json"], 30).execute(need_disable_oref=True)
    os.remove(os.path.join(myopenaps_dir + "enter_bolus.json"))

    if not is_error:
        set_bolusing(True)
    return result

@app.route("/press_keys", methods=['POST'])
@check_authorization
def press_keys():
    try:
        keys = request.get_json(force=True)["keys"]
    except KeyError:
        return '', 400

    for key in keys:
        if key not in ["esc", "act", "up", "down", "b"]:
            return '', 400

    input_file_url = os.path.join(myopenaps_dir + "buttons.json")

    with open(input_file_url, 'w') as buttons_file:
        buttons_file.write(json.dumps({"keys": keys}))

    result, _ = Command(["mdt", "button", "buttons.json"], 30).execute(need_disable_oref=True)

    os.remove(input_file_url)

    return result

@app.route("/set_temp_basal")
@check_authorization
def set_temp_basal():
    try:
        temp = request.args.get("temp")
        rate = float(request.args.get("rate"))
        duration = int(request.args.get("duration"))
    except (KeyError, ValueError):
        return '', 400
    if temp not in ["percent", "absolute"] or duration % 30 != 0:
        return '', 400

    rate = round(rate, 1)
    with open(os.path.join(myopenaps_dir + "set_temp_basal.json"), 'w') as temp_basal_file:
        temp_basal_file.write(
            '{ "temp": "{temp}", "rate": "{rate}", "duration": "{duration}" }'.format(
                    temp=temp, rate=rate, duration=duration))

    result, _ = Command(["mdt", "set_temp_basal", "set_temp_basal.json"], 30).execute(need_disable_oref=True)
    os.remove(os.path.join(myopenaps_dir + "set_temp_basal.json"))

    return result

@app.route("/suspend_pump")
@check_authorization
def suspend_pump():
    result, is_error = Command(["mdt", "suspend"], 30).execute(need_disable_oref=True)
    if not is_error:
        status_json = json.load(open(os.path.join(myopenaps_dir + "monitor/status.json")))
        status_json["suspended"] = True
        with open(os.path.join(myopenaps_dir + "monitor/status.json"), "w") as status_file:
            status_file.write(json.dumps(status_json, indent=2))

    return result

@app.route("/resume_pump")
@check_authorization
def resume_pump():
    result, is_error = Command(["mdt", "resume"], 30).execute(need_disable_oref=True)

    if not is_error:
        status_json = json.load(open(os.path.join(myopenaps_dir + "monitor/status.json")))
        status_json["suspended"] = False
        with open(os.path.join(myopenaps_dir + "monitor/status.json"), "w") as status_file:
            status_file.write(json.dumps(status_json, indent=2))

    return result


@app.route("/oref_enabled")
def oref_enabled():
    return json.dumps(read_oref_status())

@app.route("/oref_enable")
@check_authorization
def oref_enable():
    switch_oref_status(True)
    return '', 200

@app.route("/oref_disable")
@check_authorization
def oref_disable():
    switch_oref_status(False)
    return '', 200


@app.route("/reboot")
@check_authorization
def reboot():
    Thread(target=lambda: os.system("sleep 1; reboot")).start()
    return '', 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

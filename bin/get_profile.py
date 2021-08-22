#!/usr/bin/env python
"""
Module to ease work with nightscout profiles.
By default lists all profiles found, and supports following sub-commands:
* profiles - list defined profiles
* display - display named (or default) profile
    (in nightscout or OpenAPS format)
* write - write to disk profile in OpenAPS format

Bunch of things inspired by https://github.com/MarkMpn/AutotuneWeb/
"""

# Make it work on both python 2 and 3
# Probably a bit wide, but I'm still learning
from __future__ import absolute_import, with_statement, print_function, unicode_literals

# Built-in modules
import argparse
from datetime import datetime
import json
import os.path
import logging
import sys

# External modules
import requests
#from texttable import Texttable

# logging.basicConfig(level=logging.INFO)
logging.basicConfig(level=logging.DEBUG)

PROFILE_FILES = ['autotune.json', 'profile.json', 'pumpprofile.json']
PROFILE_KEYS = [
    'autosens_max', 'autosens_min', 'basalprofile', 'bg_targets', 'carb_ratio',
    'carb_ratios', 'dia', 'isfProfile', 'min_5m_carbimpact', 'timezone'
]
TIMED_ENTRIES = ['carbratio', 'sens', 'basal', 'target_low', 'target_high']


def get_profiles(nightscout, token):
    """
    Get profiles available in nightscout
    """
    # Create the URL
    r_url = nightscout + "/api/v1/profile.json"
    # If token is not None, add it to the URL
    if token is not None:
        r_url = r_url + "?" + token
    # Make the request
    r = requests.get(r_url)
    # Return the json
    return r.json()


def get_current_profile(nightscout, token, profile_name):
    """
    Try to get the active profile
    """
    # Create the URL
    r_url = nightscout + "/api/v1/profile.json"
    # If token is not None, add it to the URL
    if token is not None:
        r_url = r_url + "?" + token
    # Make the request
    p_list = requests.get(r_url).json()
    # Log the profile list
    logging.debug("profile list: %s", p_list)
    # Get the default profile
    default_profile = p_list[0]["defaultProfile"]
    # If profile_name is None, try to get the active profile
    if profile_name is None:
        # Create the URL
        p_url = (
            nightscout +
            "/api/v1/treatments.json?find[eventType][$eq]=Profile Switch&count=1"
        )
        # If token is not None, add it to the URL
        if token is not None:
            p_url = p_url + "?" + token
        # Make the request
        p_switch = requests.get(p_url).json()
        # Log the profile switch
        logging.debug("p_switch: %s", p_switch)
        # If p_switch is not empty
        if p_switch:
            # Try to get the profile from the profile switch
            try:
                # Load the profile switch json
                sw_prof = json.loads(p_switch[0]["profileJson"])
                # Log the profile switch json
                logging.debug("sw_prof: %s", sw_prof)
                # If sw_prof is not empty
                if sw_prof:
                    # Set the profile to the profile switch json
                    profile = sw_prof
                    # Set the profile name to the profile switch name
                    profile["name"] = p_switch[0]["profile"]
                    # If the profile timezone is not empty
                    if profile["timezone"] is not None:
                        # Return the profile
                        return profile
                    # Otherwise
                    else:
                        # Set the profile timezone to the default profile timezone
                        profile["timezone"] = default_profile["timezone"]
                        # Return the profile
                        return profile
            # If there is a KeyError
            except KeyError:
                # Log the default profile
                logging.debug("default profile: %s", default_profile)
                # Set the profile timezone to the default profile timezone
                profile["timezone"] = p_list[0]["store"][default_profile]["timezone"]
                # Return the profile
                return profile
#                sys.exit(
#                    """Latest 'Profile Switch' event doesn't contain profile, """ +
#                    """please specify profile name to use with --name flag.""")
        # Set the profile name to the default profile name
        p_list[0]["store"][default_profile]["name"] = default_profile
        # Try to get the units from the default profile
        try:
            # If the default profile units is not empty
            if not p_list[0]["store"][default_profile]["units"]:
                p_list[0]["store"][default_profile]["units"] = p_list[0][
                    "units"]
        except KeyError:
            # Set the units to the default profile units
            p_list[0]["store"][profile_name]["units"] = p_list[0]["units"]
        # Return the default profile
        return p_list[0]["store"][default_profile]
    # Set the profile name to the profile name
    p_list[0]["store"][profile_name]["name"] = profile_name
    # Try to get the units from the profile name
    try:
        # If the profile name units is not empty
        if not p_list[0]["store"][profile_name]["units"]:
            # Set the units to the profile name units
            p_list[0]["store"][profile_name]["units"] = p_list[0]["units"]
    # If there is a KeyError
    except KeyError:
        # Set the units to the profile name units
        p_list[0]["store"][profile_name]["units"] = p_list[0]["units"]
    # Return the profile name
    return p_list[0]["store"][profile_name]


def profiles(nightscout, token):
    """
    print list of profiles available in nightscout
    """
    # Get the profiles
    p_list = get_profiles(nightscout, token)
    # Get the default profile
    default_profile = p_list[0]["defaultProfile"]
    # Get the list of profiles
    profile_list = p_list[0]["store"].keys()
    # Print the default profile
    print("Default profile: {}".format(default_profile))
    # Print the available profiles
    print("Available profiles:")
    for profile in profile_list:
        print("\t" + profile)


def display(nightscout, token, profile_name, profile_format):
    """
    Display contents of a profile, in requested format
    """
    # Get the profile
    profile = get_current_profile(nightscout, token, profile_name)
    # If the profile format is nightscout, display the profile
    if profile_format == "nightscout":
        # display_nightscout(p_list, profile_name)
        logging.debug("Displaying profile {}".format(profile["name"]))
        print(json.dumps(profile, indent=4))
    # If the profile format is text, display the profile
    elif profile_format == "text":
        display_text(profile)
    # Otherwise, display the profile in OpenAPS format
    else:
        print(json.dumps(ns_to_oaps(profile), indent=4))


def write(nightscout, token, profile_name, directory):
    """
    Write profile in OpenAPS format to a directory
    """
    # Get the current profile
    profile = ns_to_oaps(get_current_profile(nightscout, token, profile_name))
    logging.debug("Checking for directory: %s", directory)
    if not os.path.isdir(directory):
        sys.exit(
            "Please provide an existing directory to write profile files to")
    # Check whether there's already a profile file with settings we don't have
    for profile_file in PROFILE_FILES:
        try:
            # Open the file for reading
            with open(os.path.join(directory, profile_file), 'r') as p:
                # Load the json
                old_profile = json.loads(p.read())
                # For each key in the old profile
                for key in old_profile.keys():
                    # Check whether we have that key
                    logging.debug("Checking key %s from profile file %s", key,
                                  profile_file)
                    # If we don't have that key
                    if key not in PROFILE_KEYS:
                        # Log an error
                        logging.error(
                            "Existing profile file %s contains key %s we wouldn't set!",
                            profile_file, key)
                        # And exit
                        sys.exit(
                            "Existing profile contains a key we wouldn't set!")
        # If there's no file
        except IOError:
            # Don't do anything
            pass
    # For each profile file
    for profile_file in PROFILE_FILES:
        # Open the file for writing
        with open(os.path.join(directory, profile_file), 'w') as f:
            # Write the json
            f.write(json.dumps(profile, indent=4))


def normalize_entry(entry):
    """
    Clean up an entry before further processing
    """
    # Try to get the timeAsSeconds value
    try:
        if entry["timeAsSeconds"]:
            pass
    except KeyError:
        # Get the time value
        entry_time = datetime.strptime(entry["time"], "%H:%M")
        entry[
            "timeAsSeconds"] = 3600 * entry_time.hour + 60 * entry_time.minute
    try:
        if entry["time"]:
            pass
    except KeyError:
        # Get the timeAsSeconds value
        entry_hour = int(entry['timeAsSeconds'] / 3600)
        # Get the timeAsSeconds value
        entry_minute = int(entry['timeAsSeconds'] % 60)
        # Convert the timeAsSeconds to time
        entry["time"] = str(entry_hour).rjust(
            2, '0') + ":" + str(entry_minute).rjust(2, '0')

    # Set the start value to the time value
    entry["start"] = entry["time"] + ":00"
    # Set the minutes value to the timeAsSeconds value divided by 60
    entry["minutes"] = int(entry["timeAsSeconds"]) / 60
    # Return the entry
    return entry


def ns_to_oaps(ns_profile):
    """
    Convert nightscout profile to OpenAPS format
    """
    # Create a dict to store the OpenAPS profile
    oaps_profile = {}
    # XXX If addint any new entries, make sure to update PROFILE_KEYS at the top
    # Not represented in nightscout
    oaps_profile["min_5m_carbimpact"] = 8.0
    oaps_profile["autosens_min"] = 0.7
    oaps_profile["autosens_max"] = 1.2
    oaps_profile["dia"] = float(ns_profile["dia"])
    oaps_profile["timezone"] = ns_profile["timezone"]

    # Create a list of dicts with basal profile
    oaps_profile["basalprofile"] = []
    for entry_type in TIMED_ENTRIES:
        for entry in ns_profile[entry_type]:
            normalize_entry(entry)
    for basal_item in ns_profile["basal"]:
        oaps_profile["basalprofile"].append({
            "i":
            len(oaps_profile["basalprofile"]),
            "minutes":
            basal_item["minutes"],
            "start":
            basal_item["start"],
            "rate":
            float(basal_item["value"]),
        })

    # Create a dict of dicts with target levels
    oaps_profile["bg_targets"] = {
        "units": ns_profile["units"],
        "user_preferred_units": ns_profile["units"],
        "targets": [],
    }
    targets = {}
    for low in ns_profile["target_low"]:
        low = normalize_entry(low)
        targets.setdefault(low["time"], {})
        targets[low["time"]]["low"] = {
            "i": len(targets),
            "start": low["start"],
            "offset": float(low["timeAsSeconds"]),
            "low": float(low["value"]),
        }
    for high in ns_profile["target_high"]:
        high = normalize_entry(high)
        targets.setdefault(high["time"], {})
        targets[high["time"]]["high"] = {"high": float(high["value"])}
    for time in sorted(targets.keys()):
        oaps_profile["bg_targets"]["targets"].append({
            "i":
            len(oaps_profile["bg_targets"]["targets"]),
            "start":
            targets[time]["low"]["start"],
            "offset":
            targets[time]["low"]["offset"],
            "low":
            targets[time]["low"]["low"],
            "min_bg":
            targets[time]["low"]["low"],
            "high":
            targets[time]["high"]["high"],
            "max_bg":
            targets[time]["high"]["high"],
        })

    # Create a dics of dicts with insulin sensitivity profile
    oaps_profile["isfProfile"] = {"first": 1, "sensitivities": []}
    isf_p = {}
    for sens in ns_profile["sens"]:
        sens = normalize_entry(sens)
        isf_p.setdefault(sens["time"], {})
        isf_p[sens["time"]] = {
            "sensitivity": float(sens["value"]),
            "start": sens["start"],
            "offset": sens["minutes"],
        }
    for time in sorted(isf_p.keys()):
        oaps_profile["isfProfile"]["sensitivities"].append({
            "i":
            len(oaps_profile["isfProfile"]["sensitivities"]),
            "sensitivity":
            isf_p[time]["sensitivity"],
            "offset":
            isf_p[time]["offset"],
            "start":
            isf_p[time]["start"],
        })

    # Create a dict of dicts for carb ratio
    oaps_profile["carb_ratios"] = {
        "first": 1,
        "units": "grams",
        "schedule": []
    }
    cr_p = {}
    for cr in ns_profile["carbratio"]:
        cr = normalize_entry(cr)
        cr_p.setdefault(cr["time"], {})
        cr_p[cr["time"]] = {
            "start": cr["start"],
            "offset": cr["minutes"],
            "ratio": float(cr["value"]),
        }
    for time in sorted(cr_p.keys()):
        oaps_profile["carb_ratios"]["schedule"].append({
            "i":
            len(oaps_profile["carb_ratios"]["schedule"]),
            "start":
            cr_p[time]["start"],
            "offset":
            cr_p[time]["offset"],
            "ratio":
            cr_p[time]["ratio"],
        })
    oaps_profile["carb_ratio"] = oaps_profile["carb_ratios"]["schedule"][0][
        "ratio"]

    sorted_profile = {}
    for key in sorted(oaps_profile.keys()):
        sorted_profile[key] = oaps_profile[key]

    # return oaps_profile
    return sorted_profile


def display_nightscout(profile_data, profile_name):
    """
    Display profile the way it comes from nightscout
    """
    # Print a message
    print("Displaying profile {}".format(profile_name))
    # Pretty print the json
    print(json.dumps(profile_data[0]["store"][profile_name], indent=4))


def display_text(p_data):
    """
    Display profile in text format
    """
    # p_data = profile_data[0]["store"][profile_name]
    logging.debug("Data keys: %s", p_data.keys())

    # Single value data
    #singletons = Texttable()
    #singletons.set_deco(Texttable.HEADER)
    #singletons.set_cols_align(["c", "c", "c", "c"])
    #singletons.add_rows([
        #["Profile name", "Timezone", "Units", "DIA"],
        #[
            #p_data["name"],
            #p_data["timezone"],
            #p_data["units"],
            #p_data["dia"]
        #],
    #])
    #print(singletons.draw() + "\n")

    times = {}
    tgt_low = {v["time"]: v["value"] for v in p_data["target_low"]}
    tgt_high = {v["time"]: v["value"] for v in p_data["target_high"]}
    carb_ratio = {v["time"]: v["value"] for v in p_data["carbratio"]}
    sens = {v["time"]: v["value"] for v in p_data["sens"]}
    basal = {v["time"]: v["value"] for v in p_data["basal"]}
    logging.debug(tgt_high, tgt_low, carb_ratio, sens, basal)
    for (time, basal) in basal.items():
        times.setdefault(time, {})
        times[time]["basal"] = basal
    for (time, sens) in sens.items():
        times.setdefault(time, {})
        times[time]["sens"] = sens
    for (time, c_r) in carb_ratio.items():
        times.setdefault(time, {})
        times[time]["carbratio"] = c_r
    for (time, tgt_h) in tgt_high.items():
        times.setdefault(time, {})
        times[time]["tgt_high"] = tgt_h
    for (time, tgt_l) in tgt_low.items():
        times.setdefault(time, {})
        times[time]["tgt_low"] = tgt_l
    logging.debug("Times: %s", times)

    times_list = [["Time", "Basal", "ISF", "CR", "Target Low", "Target High"]]
    for time in sorted(times.keys()):
        times_list.append([
            time,
            times[time].get("basal", ""),
            times[time].get("sens", ""),
            times[time].get("carbratio", ""),
            times[time].get("tgt_low", ""),
            times[time].get("tgt_high", ""),
        ])
    # times_table = Texttable()
    #times_table.set_cols_align(["c", "c", "c", "c", "c", "c"])
    #times_table.add_rows(times_list)
    #print(times_table.draw() + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get nightscout profile.")
    parser.add_argument(
        "--nightscout",
        help="Nightscout URL",
        required=True,
        nargs="?",
        const="http://127.0.0.1:1337",
        default="http://127.0.0.1:1337",
    )
    parser.add_argument("--token", help="Authenticaton token")

    subparsers = parser.add_subparsers(help="Sub-command to run",
                                       dest="subparser")

    parser_profiles = subparsers.add_parser("profiles",
                                            help="List all profile names")

    parser_display = subparsers.add_parser("display", help="Display a profile")
    parser_display.add_argument("--name",
                                help="Which profile to display",
                                nargs="?",
                                dest="profile_name")
    parser_display.add_argument(
        "--format",
        default="nightscout",
        nargs="?",
        dest="profile_format",
        choices=["nightscout", "openaps", "text"],
        help="What format to display profile in",
    )

    parser_write = subparsers.add_parser(
        "write", help="Write profile in OpenAPS format to a directory")
    parser_write.add_argument("--directory",
                              help="What directory to write files to",
                              required=True)
    parser_write.add_argument("--name",
                              help="Which profile to display",
                              nargs="?",
                              dest="profile_name")

    logging.debug(vars(parser.parse_args()))

    # https://stackoverflow.com/questions/4575747/get-selected-subcommand-with-argparse/44948406#44948406
    # I have no idea what it does, but it seems to do the trick
    kwargs = vars(parser.parse_args())
    globals()[kwargs.pop("subparser")](**kwargs)

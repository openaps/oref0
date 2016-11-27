<<<<<<< HEAD
# oref0

Javascript plugins for openaps

Master code coverage: [![Coverage Status](https://coveralls.io/repos/github/openaps/oref0/badge.svg?branch=master)](https://coveralls.io/github/openaps/oref0?branch=master)

Dev code coverage: [![Coverage Status](https://coveralls.io/repos/github/openaps/oref0/badge.svg?branch=dev)](https://coveralls.io/github/openaps/oref0?branch=dev)

## Installing

Install tools globally:

`sudo npm install -g oref0`

## Usage

### `oref0`
The open reference implementation of the reference design.
```
  Usage:
oref0 <cmd>

 ______   ______   ______  ______ 0
/ |  | \ | |  | \ | |     | |      
| |  | | | |__| | | |---- | |----  
\_|__|_/ |_|  \_\ |_|____ |_|      

Valid commands:
  oref0 env - print information about environment.
  oref0 pebble
  oref0 ifttt-notify
  oref0 get-profile
  oref0 calculate-iob
  oref0 determine-basal
  oref0 help - this message
```

### `mm-stick`
Tools to work with carelink stick.
```
Usage: mm-stick [{scan,diagnose,help},...]

    scan      - Print the local location of a plugged in stick.
    diagnose  - Run python -m decocare.stick $(python -m decocare.scan)
    warmup    - Runs scan and diagnose with no output.
                Exits 0 on success, non-zero exit code
                otherwise.
    insert    - Insert usbserial kernel module.
    remove    - Remove usbserial kernel module.
    udev-info - Print udev information about the stick.
    list-usb  - List usb information about the stick.
    reset-usb - Reset entire usb stack. WARNING, be careful.
    fail      - Always return a failing exit code.
    help      - This message.
```

### `mm-format-ns-glucose`
Reformat medtronic's glucose records into format Nightscout prefers.
The result is suitable for sending to Nightscout's entries api, eg, using
`ns-upload-entries`.
```
mm-format-ns-glucose <input> <output>


```

### `mm-format-ns-pump-history`
Reformat medtronic's pump history records into format Nightscout prefers.
The result is suitable for sending to Nightscout's entries api, eg, using
`ns-upload-entries`.
```
mm-format-ns-pump-history <input> <output>
```


### `ns-upload-entries`

Upload to Nightscout entries.

This requires two environment variables to be set:
Set `API_SECRET` to the hashed version of your `API_SECRET`.
Set `NIGHTSCOUT_HOST` to your Nightscout base URL.
These can be defined in crontab, or in a simple file, eg
`/etc/default/openaps`.

```
API_SECRET="..." NIGHTSCOUT_HOST=localhost:1337 ns-upload-entries <input> <output>

```

## Contributing

See the [CONTRIBUTING document](CONTRIBUTING.md)
### Get the source

```
git clone git://github.com/openaps/oref0.git
git checkout dev
git checkout -b wip/my-enhancement-fix-or-proposal
```

This command installs new versions from source:
`sudo npm install -g`

Alternately, `sudo npm link` or `sudo npm link oref0` should allow you to
edit from your checkout while using your checkout globally on your system.

### Fork on github.

Fork the repository on github. Add your personal "remote" with something like
this:

```
git remote rename origin author
git remote add origin git@github.com:<github-user>/oref0.git
git push origin -u wip/my-enhancement-fix-or-proposal
```
Then target our `dev` branch for a pull request/peer review.


## openaps

This is part of a series of tools to support a self-driven DIY
implementation based on the OpenAPS reference design. The tools may be
categorized as *monitor* (collecting data about environment, and
operational status of devices and/or aggregating as much data as is
relevant into one place), *predict* (make predictions about what should
happen next), or *control* (enacting changes, and feeding more data back
into the *monitor*). 

By proceeding using these tools or any piece within, you agree to the
copyright (see LICENSE.txt for more information) and release any
contributors from liability. 

*Note:* This is intended to be a set of tools to support a self-driven DIY
implementation and any person choosing to use these tools is solely
responsible for testing and implement these tools independently or
together as a system.  The [DIY part of OpenAPS is important]
(http://bit.ly/1NBbZtO). While formal training or experience as an
engineer or a developer is not required, what *is* required is a growth
mindset to learn what are essentially "building blocks" to implement an
OpenAPS instance. This is not a "set and forget" system; it requires
diligent and consistent testing and monitoring to ensure each piece of
the system is monitoring, predicting, and performing as desired.  The
performance and quality of your system lies solely with you.
=======

# openaps utility belt

These are the [core utilities][proposal] needed to develop an open source
artificial pancreas.

This is part of a series of tools to support a self-driven DIY
implementation based on the OpenAPS reference design. The tools may be
categorized as *monitor* (collecting data about environment, and
operational status of devices and/or aggregating as much data as is
relevant into one place), *predict* (make predictions about what should
happen next), or *control* (enacting changes, and feeding more data back
into the *monitor*). 

By proceeding using these tools or any piece within, you agree to the
copyright (see LICENSE.txt for more information) and release any
contributors from liability. 

Check out [the openaps docs][the openaps docs] to help get you started.

*Note:* This is intended to be a set of tools to support a self-driven DIY
implementation and any person choosing to use these tools is solely
responsible for testing and implement these tools independently or
together as a system.  The [DIY part of OpenAPS is important]
(http://bit.ly/1NBbZtO). While formal training or experience as an
engineer or a developer is not required, what *is* required is a growth
mindset to learn what are essentially "building blocks" to implement an
OpenAPS instance. This is not a "set and forget" system; it requires
diligent and consistent testing and monitoring to ensure each piece of
the system is monitoring, predicting, and performing as desired.  The
performance and quality of your system lies solely with you.

Additionally, this community of contributors believes in "paying it
forward", and individuals who are implementing these tools are asked to
contribute by asking questions, helping improve documentation, and
contribute in other ways.

[GettingStarted]: https://github.com/openaps/openaps/wiki/GettingStarted
[wiki]: https://github.com/openaps/openaps/wiki
[proposal]: https://gist.github.com/bewest/a690eaf35c69be898711
[the openaps docs]: https://github.com/openaps/docs

![openaps loop hardware](https://cloud.githubusercontent.com/assets/394179/9372378/c2023bc2-4692-11e5-8254-fe940f847536.png)

This is not an artificial pancreas, but rather tools which independently allow:

* monitor - Collect data about environment, and operational status of devices.
  Aggregate as much data relevant to therapy as possible into one place.
  We propose a tool, `openaps-use` as a proof of concept.

* predict - Can make predictions about what should happen next.

* control - Can enact changes in the world: emails, placing phone calls, SMS,
  issuing commands to pumps.


## Install

There are two ways to install openaps, from source, and as a python package via
setuptools.

The following apt-get dependencies are required (they can be installed through
variety of means, in debian/ubuntu and apt based systems the following packages
are recommended/required:

    sudo apt-get install python python-dev python-setuptools python-software-properties python-numpy


#### From source

See [GettingStarted][GettingStarted] for more important information
about versions of software dependencies, but to install from source
clone this repo, and issue:

    sudo python setup.py develop

#### From pypi

To [install from pypi](https://pypi.python.org/pypi/openaps):

    sudo pip install -U openaps

This installs `openaps` system wide.
Do not use `openaps` commands in the the openaps repo.  Only use the
`openaps` directory for hacking on the core library, or for managing
upgrades through git.  Running `openaps` inside of the openaps
source directory will error in the best case, and mess up your
`openaps` install in the worst case.

##### Updating

    sudo easy_install -ZU openaps

### Usage

    usage: openaps [-h] [-c C C] [-C CONFIG] [--version] [command] ...

#### openaps - openaps: a toolkit for DIY artificial pancreas system

##### positional arguments:
  * command
  * args

optional arguments:

    -h, --help            show this help message and exit
    -c C C
    -C CONFIG, --config CONFIG
    --version             show program's version number and exit

  Utilities for developing an artificial pancreas system.
  openaps helps you manage and structure reports for various devices.


All of the `device` and `report` `add` and `show` commands modify
`openaps.ini` in the current working directory, which is assumed to be
a git repo explicitily dedicated to helping develop and configure a
`DIY` artificial pancreas system.  This means `openaps` is an SDK for
an artificial pancreas system, not an artificial pancreas system.

See `openaps init` for setting up a brand new instance of your own
`openaps`, or see the notes below for details on how to convert an
existing git repo into an instance of `openaps`.

## Common workflows:

    openaps init
    openaps device <cmd>
      
      Device commands allow you to match a device driver, with a name
      and a configuration.
      
      add     - add device config to `openaps.ini`
      remove  - remove device from `openaps.ini`
      show    - print device uri, list all by default

    openaps use [--format <json,stdout,text>]
                [--output <filename>]
            <device>
            <use>
            [use-args...]

      For each device registered, the vendor implementation provides a
      number of uses.  This allows users to experiment with reports.

    openaps report <cmd>

      Reports match a device use to a format and filename.

      add     - add report config to `openaps.ini`
      remove  - remove report from `openaps.ini`
      show    - print report uri, list all by default
      invoke  - run and save report in file

### Init new openaps environment

Do not use `openaps` commands in the the openaps repo.  Only use the
`openaps` directory for hacking on the core library, or for managing
upgrades through git.  Instead change to a new directory, not managed
by git: `cd ~/Documents`.

Setup of new instance:  

    openaps init myopenaps    - this creates an instance of openaps in a new
                                directory, called myopenaps
    

    cd myopenaps - change directory to root of new repo

A valid instance of openaps is a git repo with a file called
`openaps.ini` present.

`openaps` will track configuration and some status information inside of
`openaps.ini`.

### Init existing git repo as openaps-environment 

If you already have a git repo which you would like to
become a valid openaps environent, in the root of your repo, run:

    touch openaps.ini
    git add openaps.ini
    git commit -avm 'init openaps'

Now, wth a valid `openaps` environment, you can register **device**s for
use.  A **device** is implemented by a **vendor**.  `openaps` provides a
modular, language and process independent environment for creating
vendors and devices.

### Managing devices

To register devices for use, see `openaps device` commands:

    openaps device -h
    openaps device add <name> <vendor> [opts...]
    eg:
    # register a medtronic device named pump
    openaps device add pump medtronic 665455
    # register a dexcom device named cgm
    openaps device add cgm dexcom

### Using devices
Now that devices are known, and we have a variety of commands
available.  We can explore how to produce reports by using devices
with the `openaps use` command:

    openaps use <device-name> <use-name> [opts]

`openaps use` commands can only be used after devices have been added to
the `openaps.ini` config using `openaps device add`.
Eg:

    openaps use pump -h        - show available commands for the
                                 device known as "pump"
    openaps use pump iter_pump 100 - get last 100 pump history records
                                 from the device called pump
    openaps use cgm -h         - show available commands for the
                                 device known as "cgm"
    openaps use cgm glucose

### Save reports
After experimenting with `openaps use` commands, users can save reports
using the `openaps report` commands.
`openaps report` commands map `openaps use` commands to filenames:

#### `openaps report add`

Adding a report means configuring a `use` command with a format and a
output, most commonly, a filename is used as the output.

    openaps report add <report-name> <report-formatter> <device> <use> [opts]

    # add a report, saved in a file called pump-history.json, which is
    # JSON format, from device pump using use iter_pump.
    openaps report add pump-history.json JSON pump iter_pump 100

    # add a report, saved in a file called glucose.json, which is
    # JSON format, from device cgm using use glucose.
    openaps report add glucose.json JSON cgm glucose

### `invoke` reports to run and save the results of the `use`

#### `openaps report invoke`

Invoking a report means running a `use` command according to it's
configuration.

    # invoke the report to create glucose.json
    openaps report invoke glucose.json

    # invoke the report to create pump-history.json
    openaps report invoke pump-history.json

All commands support tab completion, and -h help options to help
explore the live help system.


### Sample `use` commands

#### `medtronic`

Assuming device is named `pump`:

    usage: openaps-use pump [-h]
                            {Session, bolus, iter_glucose, iter_pump,
                            model, mytest, read_basal_profile_A,
                            read_basal_profile_B,
                            read_basal_profile_std, read_carb_ratios,
                            read_clock, read_current_glucose_pages,
                            read_current_history_pages,
                            read_glucose_data, read_history_data,
                            read_selected_basal_profile,
                            read_settings, read_status,
                            read_temp_basal, reservoir, resume_pump,
                            scan, set_temp_basal, settings, status,
                            suspend_pump}
                            ...

    positional arguments:
      {Session, bolus, iter_glucose, iter_pump, model, mytest,
      read_basal_profile_A, read_basal_profile_B,
      read_basal_profile_std, read_carb_ratios, read_clock,
      read_current_glucose_pages, read_current_history_pages,
      read_glucose_data, read_history_data,
      read_selected_basal_profile, read_settings, read_status,
      read_temp_basal, reservoir, resume_pump, scan, set_temp_basal,
      settings, status, suspend_pump}
                            Operation
        Session             session for pump
        bolus               Send bolus.
        iter_glucose        Read latest 100 glucose records
        iter_pump           Read latest 100 pump records
        model               Get model number
        mytest              Testing read_settings
        read_basal_profile_A
                            Read basal profile A.
        read_basal_profile_B
                            Read basal profile B.
        read_basal_profile_std
                            Read default basal profile.
        read_carb_ratios    Read carb_ratios.
        read_clock          Read date/time of pump
        read_current_glucose_pages
                            Read current glucose pages.
        read_current_history_pages
                            Read current history pages.
        read_glucose_data   Read pump glucose page
        read_history_data   Read pump history page
        read_selected_basal_profile
                            Fetch the currently selected basal profile.
        read_settings       Read settings.
        read_status         Get pump status
        read_temp_basal     Read temporary basal rates.
        reservoir           Get pump remaining insulin
        resume_pump         resume pumping.
        scan                scan for usb stick
        set_temp_basal      Set temporary basal rates.
        settings            Get pump settings
        status              Get pump status (alias for read_status)
        suspend_pump        Suspend pumping.

    optional arguments:
      -h, --help            show this help message and exit

Some commands like `read_glucose_data`, `read_history_data` take a
`page` parameter, describing which page to fetch.

Some commands like `bolus`, `set_temp_basal`, take an `input`
parameter which may be `-` for `stdin` or a filename containing a json
data structure which represents the request.

All commands support `-h` and `--help` output.

#### `dexcom`


    usage: openaps-use cgm [-h] {glucose,iter_glucose,scan} ...

    positional arguments:
      {glucose,iter_glucose,scan}
                            Operation
        glucose             glucose (will pull all records)
        iter_glucose <n>       glucose ('n' for the number of records you want)
        scan                scan for usb stick

    optional arguments:
      -h, --help            show this help message and exit

## License
MIT License

Copyright (c) 2016 Ben West
Copyright (c) 2015 Ben West

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

>>>>>>> 43401bc3046ccaf4ec65db282e638bd9be2b760a

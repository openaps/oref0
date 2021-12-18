# oref0

Algorithm for OpenAPS implementations. To get started with OpenAPS, see the [OpenAPS documentation](http://openaps.readthedocs.org/en/latest/)

## Installing oref0

Install tools globally:

`npm run global-install`

## Usage of oref0

### `oref0`

<details>
    <summary>The open reference implementation of the reference design. (click to expand for more usage details)</summary>
<br>
  
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

### Get the source

```
git clone https://github.com/openaps/oref0.git
cd oref0
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

</details>

## Contributing

See the [CONTRIBUTING document](CONTRIBUTING.md). PRs welcome!

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
together as a system.  The [DIY part of OpenAPS is important](http://bit.ly/1NBbZtO).
While formal training or experience as an
engineer or a developer is not required, what *is* required is a growth
mindset to learn what are essentially "building blocks" to implement an
OpenAPS instance. This is not a "set and forget" system; it requires
diligent and consistent testing and monitoring to ensure each piece of
the system is monitoring, predicting, and performing as desired.  The
performance and quality of your system lies solely with you. 

Read the [OpenAPS documentation](http://openaps.readthedocs.io/en/latest/) for more details.

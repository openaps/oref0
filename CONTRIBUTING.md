
# Contributing to openaps

Thanks for being a part of openaps.

OpenAPS is a series of tools to support a self-driven DIY
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

Additionally, this community of contributors believes in "paying it
forward", and individuals who are implementing these tools are asked to
contribute by asking questions, helping improve documentation, and
contribute in other ways. We always need testers for various pieces of works-in-progress; please do ask if you would like to help but aren't sure where to get started. 

Please submit issues and pull requests so that all users can share
knowledge. If you're unfamiliar with GitHub and/or coding, [check out these other ways to get involved with OpenAPS.](http://openaps.readthedocs.io/en/latest/docs/Give%20Back-Pay%20It%20Forward/contribute.html)

See [OpenAPS.org](http://OpenAPS.org/) for background on the OpenAPS movement and project.

## Using VSCode devcontainer (with docker)

This is the recommanded way in order to develop in a standard development environment without installing dependencies in your host system.

[VSCode](https://code.visualstudio.com) should automatically recognize the [devcontainer](https://code.visualstudio.com/docs/devcontainers/containers) setup, building the image for development environment.

The default container timezone is `Europe/Rome`.  
This allows to test dates timezone logic.

### Setup

Install dependencies and compile typescript files.

```
$ npm install && npm run build
```

## Build with docker

If you just need to build the library, you can use docker compose:

```
$ docker compose run --rm node sh -c "npm install && npm run build"
```

The output directory of `lib/*` will be `dist/`.

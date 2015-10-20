
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
contribute in other ways.

Please submit issues and pull requests so that all users can share
knowledge. If you're unfamiliar with GitHub and/or coding, [check out these other ways to get involved with OpenAPS.](https://openaps.gitbooks.io/building-an-open-artificial-pancreas-system/content/docs/Overview/contribute.html)

For hacking on openaps, here are some tips to help your patches reach
more people more quickly.  The `master` branch is special, it should
be "production" ready code, tested and verified, and should match the
contents available in pypi.  Basically that means the `master` branch
is never touched directly, but rather we use a variety of other
branches to do things, and then merge the work into the `master`
branch.  Sometimes this is called
[git flow](http://nvie.com/posts/a-successful-git-branching-model/).
Here's few guidelines that might help:
  
  * target a `dev` branch for pull requests.  The latest updated
    branch, especially any recently updated branch with `dev` in the
    name.
  * Avoid editing `master` branch.
  * test changes

See [OpenAPS.org](http://OpenAPS.org/) for background on the OpenAPS movement and project.


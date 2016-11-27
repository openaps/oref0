<<<<<<< HEAD
TESTS=tests/*.js
ISTANBUL=./node_modules/.bin/istanbul
MOCHA=./node_modules/mocha/bin/_mocha
ANALYZED=./coverage/lcov.info

all: test

report:
	# report results to community
test:
	./node_modules/.bin/mocha ${TESTS}

travis:
	${ISTANBUL} cover ${MOCHA} --include-all-sources true --report lcovonly -- -R tap ${TESTS}

report:
	test -f ${ANALYZED} && \
	(npm install coveralls && cat ${ANALYZED} | \
	./node_modules/.bin/coveralls) || echo "NO COVERAGE"
	test -f ${ANALYZED} && \
	(npm install codacy-coverage && cat ${ANALYZED} | \
	YOURPACKAGE_COVERAGE=1 ./node_modules/codacy-coverage/bin/codacy-coverage.js) || echo "NO COVERAGE"

=======

TESTS = $(wildcard openaps/*.py openaps/*/*.py)

test:
	python -m nose
	openaps -h
	# python -m doctest discover
	# do the test dance

ci-test: test
	# do the travis dance


.PHONY: test
>>>>>>> 43401bc3046ccaf4ec65db282e638bd9be2b760a

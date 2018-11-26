TESTS=tests/*.js
ISTANBUL=./node_modules/.bin/istanbul
MOCHA=./node_modules/mocha/bin/_mocha
ANALYZED=./coverage/lcov.info

all: test

report:
	# report results to community
test:
	./node_modules/.bin/mocha -c ${TESTS}

travis:
	${ISTANBUL} cover ${MOCHA} --include-all-sources true --report lcovonly -- -R tap ${TESTS}

report:
	test -f ${ANALYZED} && \
	(npm install coveralls && cat ${ANALYZED} | \
	./node_modules/.bin/coveralls) || echo "NO COVERAGE"
	test -f ${ANALYZED} && \
	(npm install codacy-coverage && cat ${ANALYZED} | \
	YOURPACKAGE_COVERAGE=1 ./node_modules/codacy-coverage/bin/codacy-coverage.js) || echo "NO COVERAGE"


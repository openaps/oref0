TESTS=tests/*.js

all: test

test:
	./node_modules/.bin/mocha ${TESTS}

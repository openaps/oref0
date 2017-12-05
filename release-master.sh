git checkout master && \
git pull origin master && \
npm version patch && \
git tag -l && \
echo Publishing in 10s: Ctrl-C to cancel && \
sleep 10 && \
npm publish && \
git push --tags origin master

ARG NODE_VERSION="20-slim"
FROM node:${NODE_VERSION}
RUN apt update -y && apt install -y openssh-client curl zsh git vim make jq python3
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" \
    && chsh -s $(which zsh)
COPY .zshrc /root/.zshrc
RUN corepack enable
ENV TZ='Europe/Rome' 

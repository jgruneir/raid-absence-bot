FROM python:3
FROM gorialis/discord.py

RUN mkdir -p /usr/src/bot
WORKDIR /usr/src/bot

RUN pip3 install python-dotenv
RUN pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

COPY . .

CMD [ "python3", "bot.py" ]
#!/usr/local/bin/python3

import json
from queue import Queue
from BanProcessor import BanThread
from GelfListener import GelfThread
from WebServer import ServerThread
import DiscordBot as discord

notifsQueue = Queue()

with open("config.json") as file:
    cfg = json.load(file)

banUpdate = BanThread(cfg, notifsQueue)
banUpdate.start()

gelfThread = GelfThread(cfg, notifsQueue)
gelfThread.start()

serverThread = ServerThread(cfg, notifsQueue)
serverThread.start()

discord.config(cfg, notifsQueue)
discord.run()
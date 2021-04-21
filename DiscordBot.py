import discord
import asyncio
import threading
import time
from dbHelper import sql
from datetime import datetime
import math
from BanProcessor import processBan, updatePfsense

client = discord.Client()
notifsQueue = None
cfg = {}


async def startDiscord(token):
    await client.start(token)


def stopDiscord():
    discord_loop.call_soon_threadsafe(discord_loop.stop)


async def sendDiscordMessageAsync(channel, message):
    await client.get_channel(channel).send(message)


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    conn = sql(
        host=cfg["db_host"],
        user=cfg["db_user"],
        password=cfg["db_password"],
        database=cfg["db_name"],
    )
    cursor = conn.cursor()
    if message.content[0:5] == "!ban ":
        data = {
            "ip": message.content[5:],
            "level": 4,
            "country": "",
            "city": "",
            "rule": "manual",
        }
        processBan(data, cursor, notifsQueue)
        conn.commit()
        if cursor.rowcount > 0:
            updatePfsense(cfg, cursor)
            await message.channel.send("OK")
        else:
            await message.channel.send("ERR")
    elif message.content[0:7] == "!unban ":
        cursor.execute(
            "DELETE FROM ip WHERE ip = %(ip)s",
            {"ip": message.content[7:]},
        )
        conn.commit()
        if cursor.rowcount > 0:
            updatePfsense(cfg, cursor)
            await message.channel.send("OK")
        else:
            await message.channel.send("ERR")
    elif message.content[0:5] == "!list":
        cursor.execute(
            "SELECT ip, country, city, level, rule, timestamp as datetime "
            "FROM ban b INNER JOIN ip i ON (b.idIP = i.idIP) "
            "WHERE banned = 1 "
            "GROUP BY ip "
            "ORDER BY timestamp DESC"
            "LIMIT 15;"
        )
        msg = "```"
        msg += (
            centerSpaces("IP Address", 16)
            + " | Country | "
            + centerSpaces("City", 15)
            + " | Level | "
            + centerSpaces("Rule", 10)
            + " | "
            + centerSpaces("Date", 19)
            + "\n"
        )
        for i in cursor.fetchall():
            msg += (
                centerSpaces(i["ip"], 16)
                + " | "
                + centerSpaces(i["country"], 7)
                + " | "
                + centerSpaces(i["city"], 15)
                + " | "
                + centerSpaces(str(i["level"]), 5)
                + " | "
                + centerSpaces(i["rule"], 10)
                + " | "
                + datetime.fromtimestamp(i["datetime"]).strftime("%d/%m/%Y %H:%M:%S")
                + " \n"
            )
        msg += "```"
        await message.channel.send(msg)


@client.event
async def on_ready():
    print("Discord bot logged in as: %s, %s" % (client.user.name, client.user.id))


def centerSpaces(txt, length):
    l = len(txt)
    left = math.floor((length - l) / 2)
    right = left + (length - l) % 2
    return (" " * left) + txt + (" " * right)


def config(c: dict, n):
    global notifsQueue, cfg
    notifsQueue = n
    cfg = c


def run():
    if cfg["bot_token"] is not None and cfg["bot_token"] != "":
        asyncio.get_child_watcher()
        global discord_loop
        discord_loop = asyncio.get_event_loop()
        thread = threading.Thread(target=discord_loop.run_forever)
        thread.start()
        asyncio.run_coroutine_threadsafe(startDiscord(cfg["bot_token"]), discord_loop)

    while True:
        time.sleep(20)
        data = notifsQueue.get()
        if data is not None and cfg["enable_ban_notif"]:
            msg = "IP " + data[0]
            if data[1] is not None and data[1] != "":
                msg += " FROM " + data[1]
            if data[2] is not None and data[2] != "":
                msg += ", " + data[2]
            msg += " was blocked"
            if data[3] is not None and data[3] != "":
                msg += " by rule " + data[3]
            msg += " (level " + str(data[4]) + ")"
            asyncio.run_coroutine_threadsafe(
                sendDiscordMessageAsync(cfg["bot_channel"], msg), discord_loop
            )

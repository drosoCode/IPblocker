import threading
import time
from PfsenseFauxapi.PfsenseFauxapi import PfsenseFauxapi
from dbHelper import sql
from queue import Queue
from datetime import datetime
import re


class BanThread(threading.Thread):
    def __init__(self, cfg, notifsQueue):
        threading.Thread.__init__(self)
        self._cfg = cfg
        self._continue = True
        self._notifsQueue = notifsQueue
        BanThread.ipData = ""
        BanThread.lastUpdate = datetime.now()

    def stop(self):
        self._continue = False

    def run(self):
        print("check bans started")
        while self._continue:
            time.sleep(self._cfg["check_interval"])
            self.checkBanTable()

    def checkBanTable(self):
        print("checking bans")
        conn = sql(
            host=self._cfg["db_host"],
            user=self._cfg["db_user"],
            password=self._cfg["db_password"],
            database=self._cfg["db_name"],
        )
        cursor = conn.cursor()

        # delete outdated level 1 bans warnings
        cursor.execute(
            "DELETE FROM ban WHERE level = 1 AND banned = 0 AND timestamp < %(time)s;",
            {"time": int(time.time()) - self._cfg["level_1_detect_time"]},
        )
        # delete outdated level 2 bans warnings
        cursor.execute(
            "DELETE FROM ban WHERE level = 2 AND banned = 0 AND timestamp < %(time)s;",
            {"time": int(time.time()) - self._cfg["level_2_detect_time"]},
        )
        # delete expired level 1 bans
        cursor.execute(
            "DELETE FROM ban WHERE level = 1 AND banned = 1 AND timestamp < %(time)s;",
            {"time": int(time.time()) - self._cfg["level_1_ban_time"]},
        )
        # delete expired level 2 bans
        cursor.execute(
            "DELETE FROM ban WHERE level = 2 AND banned = 1 AND timestamp < %(time)s;",
            {"time": int(time.time()) - self._cfg["level_2_ban_time"]},
        )
        # delete expired level 3 bans
        cursor.execute(
            "DELETE FROM ban WHERE level = 2 AND banned = 1 AND timestamp < %(time)s;",
            {"time": int(time.time()) - self._cfg["level_3_ban_time"]},
        )
        # delete ip without any ban rule
        cursor.execute("DELETE FROM ip WHERE idIP NOT IN (SELECT idIP FROM ban);")

        cursor.execute(
            "SELECT idIP, SUM(IF(level=1,1,0)) AS lvl1, SUM(IF(level=2,1,0)) AS lvl2 "
            "FROM ban "
            "WHERE banned = 0 "
            "GROUP BY idIP;"
        )
        for ip in cursor.fetchall():
            if ip["lvl2"] >= self._cfg["level_2_detect_nb"] or (
                ip["lvl2"] > 0
                and ip["lvl2"] + ip["lvl1"] // self._cfg["level_2_detect_nb_lvl1"]
                >= self._cfg["level_2_detect_nb"]
            ):
                # ban lvl2
                cursor.execute(
                    "SELECT ip, rule, country, city FROM ip i, ban b WHERE i.idIP = b.idIP AND i.idIP = %(idIP)s ORDER BY timestamp LIMIT 1;",
                    {"idIP": ip["idIP"]},
                )
                ipData = cursor.fetchone()
                cursor.execute(
                    "DELETE FROM ban WHERE idIP = %(idIP)s;", {"idIP": ip["idIP"]}
                )
                cursor.execute(
                    "INSERT INTO ban (idIP, level, rule, timestamp, banned) VALUES (%(idIP)s, 2, %(rule)s, %(timestamp)s, %(banned)s)",
                    {
                        "idIP": ip["idIP"],
                        "rule": ipData["rule"],
                        "timestamp": int(time.time()),
                        "banned": 1,
                    },
                )
                self._notifsQueue.put(
                    (ipData["ip"], ipData["country"], ipData["city"], ipData["rule"], 2)
                )
            elif ip["lvl1"] >= self._cfg["level_1_detect_nb"]:
                # ban lvl1
                cursor.execute(
                    "SELECT ip, rule, country, city FROM ip i, ban b WHERE i.idIP = b.idIP AND i.idIP = %(idIP)s ORDER BY timestamp LIMIT 1;",
                    {"idIP": ip["idIP"]},
                )
                ipData = cursor.fetchone()
                cursor.execute(
                    "DELETE FROM ban WHERE idIP = %(idIP)s;", {"idIP": ip["idIP"]}
                )
                cursor.execute(
                    "INSERT INTO ban (idIP, level, rule, timestamp, banned) VALUES (%(idIP)s, 1, %(rule)s, %(timestamp)s, %(banned)s)",
                    {
                        "idIP": ip["idIP"],
                        "rule": ipData["rule"],
                        "timestamp": int(time.time()),
                        "banned": 1,
                    },
                )
                self._notifsQueue.put(
                    (ipData["ip"], ipData["country"], ipData["city"], ipData["rule"], 1)
                )

            conn.commit()
            updatePfsense(self._cfg, cursor)


def processBan(data: dict, cursor, notifsQueue):
    print("processing ban")
    if not re.match("^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", data["ip"]):
        return

    banned = 0
    if int(data["level"]) >= 3:
        banned = 1

    cursor.execute(
        "INSERT INTO ip (ip, country, city) SELECT %(ip)s, %(country)s, %(city)s FROM DUAL WHERE (SELECT COUNT(*) FROM ip WHERE ip = %(ip)s) = 0;",
        {"ip": data["ip"], "country": data["country"], "city": data["city"]},
    )

    if banned == 1:
        cursor.execute(
            "SELECT idBan FROM ban b INNER JOIN ip i ON (b.idIP = i.idIP) WHERE ip = %(ip)s",
            {"ip": data["ip"]},
        )
        resp = cursor.fetchone()
        if resp is not None and "idBan" in resp:
            print("exisiting ban")
            cursor.execute(
                "UPDATE ban SET level = %(level)s, rule = %(rule)s, timestamp = %(timestamp)s, banned = 1 WHERE idBan = %(idBan)s;",
                {
                    "idBan": resp["idBan"],
                    "level": data["level"],
                    "rule": data["rule"],
                    "timestamp": int(time.time()),
                    "banned": banned,
                },
            )
        else:
            print("new ban")
            cursor.execute(
                "INSERT INTO ban (idIP, level, rule, timestamp, banned) SELECT idIP, %(level)s, %(rule)s, %(timestamp)s, %(banned)s FROM ip WHERE ip = %(ip)s;",
                {
                    "ip": data["ip"],
                    "level": data["level"],
                    "rule": data["rule"],
                    "timestamp": int(time.time()),
                    "banned": banned,
                },
            )
            notifsQueue.put(
                (data["ip"], data["country"], data["city"], data["rule"], data["level"])
            )
    else:
        cursor.execute(
            "INSERT INTO ban (idIP, level, rule, timestamp, banned) SELECT idIP, %(level)s, %(rule)s, %(timestamp)s, %(banned)s FROM ip WHERE ip = %(ip)s;",
            {
                "ip": data["ip"],
                "level": data["level"],
                "rule": data["rule"],
                "timestamp": int(time.time()),
                "banned": banned,
            },
        )


def updatePfsense(cfg, cursor):
    print("updating pfsense")
    cursor.execute(
        "SELECT DISTINCT ip FROM ip i INNER JOIN ban b ON (i.idIP = b.idIP) WHERE banned = 1"
    )
    data = " ".join(map(lambda x: x["ip"], cursor.fetchall()))

    if data != BanThread.ipData:
        print("new data ")
        FauxapiLib = PfsenseFauxapi(
            cfg["fauxapi_host"],
            cfg["fauxapi_apikey"],
            cfg["fauxapi_apisecret"],
        )
        system_config = FauxapiLib.config_get()
        for i in range(len(system_config["aliases"]["alias"])):
            if (
                system_config["aliases"]["alias"][i]["name"]
                == cfg["fauxapi_alias_name"]
            ):
                system_config["aliases"]["alias"][i]["address"] = data
                print(data)

        print(FauxapiLib.config_set(system_config))
        print(FauxapiLib.send_event("filter reload"))
        BanThread.ipData = data
        BanThread.lastUpdate = datetime.now()

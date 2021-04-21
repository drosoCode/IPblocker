import zlib
import json
import socket
import ipaddress
import threading
import time
from dbHelper import sql
from queue import Queue
from BanProcessor import processBan, updateOpnsense


class GelfThread(threading.Thread):
    def __init__(self, cfg, notifsQueue):
        threading.Thread.__init__(self)
        self._cfg = cfg
        self._continue = True
        self._notifsQueue = notifsQueue
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((cfg["gelf_bind_addr"], cfg["gelf_port"]))

    def stop(self):
        self._continue = False

    def run(self):
        print("check gelf started")
        while self._continue:
            data, addr = self._sock.recvfrom(8192)
            self.processMessage(json.loads(zlib.decompress(data, 15 + 32)))

    def processMessage(self, msg: dict):
        print("processing message")
        print(msg)
        data = {}
        if "_fields" in msg:
            msg.update(json.loads(msg["_fields"]))
        data["ip"] = msg.get("_IPV4") or msg.get("IPV4")
        data["level"] = msg.get("_threat_level") or msg.get("threat_level")
        if (
            data["ip"] is None
            or data["level"] is None
            and not ipaddress.IPv4Address(data["ip"]).is_private
        ):
            return
        data["country"] = msg.get("_src_ip_geo_country") or ""
        data["city"] = msg.get("_src_ip_geo_city") or ""
        data["rule"] = msg.get("_threat_rule") or msg.get("threat_rule") or ""

        conn = sql(
            host=self._cfg["db_host"],
            user=self._cfg["db_user"],
            password=self._cfg["db_password"],
            database=self._cfg["db_name"],
        )
        cursor = conn.cursor()
        processBan(data, cursor, self._notifsQueue)
        conn.commit()
        updateOpnsense(self._cfg, cursor)

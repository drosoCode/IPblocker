from dbHelper import sql
import threading
from flask import Flask, render_template, request
from datetime import datetime
from BanProcessor import BanThread, processBan, updatePfsense

startDate = datetime.now()


class ServerThread(threading.Thread):
    app = Flask(__name__)

    def __init__(self, cfg, notifsQueue):
        threading.Thread.__init__(self)
        ServerThread.cfg = cfg
        ServerThread.notifsQueue = notifsQueue

    @app.route("/")
    def index():
        conn = sql(
            host=ServerThread.cfg["db_host"],
            user=ServerThread.cfg["db_user"],
            password=ServerThread.cfg["db_password"],
            database=ServerThread.cfg["db_name"],
        )
        cursor = conn.cursor()

        cursor.execute(
            "SELECT SUM(IF(level=1,1,0)) AS lvl1, SUM(IF(level=2,1,0)) AS lvl2, SUM(IF(level=3,1,0)) AS lvl3, SUM(IF(level=4,1,0)) AS lvl4 "
            "FROM ban "
            "WHERE banned = 1 "
        )
        ban_c = cursor.fetchone()
        bans_count_max = sum(map(lambda x: int(ban_c[x]), ban_c.keys()))

        cursor.execute(
            "SELECT COUNT(*) AS nb, country "
            "FROM ban b INNER JOIN ip i ON (i.idIP = b.idIP) "
            "WHERE banned = 1 "
            "GROUP BY country "
            "ORDER BY nb DESC "
            "LIMIT 3;"
        )
        ban_countries = cursor.fetchall()
        ban_countries_max = sum(map(lambda x: int(x["nb"]), ban_countries))

        return render_template(
            "index.html",
            up_since=startDate.strftime("%d/%m/%Y %H:%M:%S"),
            pf_update=BanThread.lastUpdate.strftime("%d/%m/%Y %H:%M:%S"),
            bans_count=ban_c,
            bans_count_max=bans_count_max,
            ban_countries=ban_countries,
            ban_countries_max=ban_countries_max,
        )

    @app.route("/logs")
    def logs():
        conn = sql(
            host=ServerThread.cfg["db_host"],
            user=ServerThread.cfg["db_user"],
            password=ServerThread.cfg["db_password"],
            database=ServerThread.cfg["db_name"],
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ip, country, city, level, rule, timestamp as datetime "
            "FROM ban b INNER JOIN ip i ON (b.idIP = i.idIP) "
            "WHERE banned = 1 "
            "GROUP BY ip "
            "ORDER BY level DESC, timestamp DESC;"
        )
        data = cursor.fetchall()
        for i in range(len(data)):
            data[i]["datetime"] = datetime.fromtimestamp(data[i]["datetime"]).strftime(
                "%d/%m/%Y %H:%M:%S"
            )

        return render_template("logs.html", logs=data)

    @app.route("/admin", methods=["GET", "POST"])
    def admin():
        alert_type = ""
        alert_txt = ""
        conn = sql(
            host=ServerThread.cfg["db_host"],
            user=ServerThread.cfg["db_user"],
            password=ServerThread.cfg["db_password"],
            database=ServerThread.cfg["db_name"],
        )
        cursor = conn.cursor()

        if request.method == "POST":
            if "delete_ip_id" in request.form:
                cursor.execute(
                    "DELETE FROM ip WHERE idIP = %(idIP)s",
                    {"idIP": request.form["delete_ip_id"]},
                )
                conn.commit()
                if cursor.rowcount > 0:
                    updatePfsense(ServerThread.cfg, cursor)
                    alert_type = "success"
                    alert_txt = "IP unbanned successfully"
                else:
                    alert_type = "danger"
                    alert_txt = "Failed to unban IP"
            elif "add_ip" in request.form:
                data = {
                    "ip": request.form["add_ip"],
                    "level": 4,
                    "country": "",
                    "city": "",
                    "rule": "manual",
                }
                processBan(data, cursor, ServerThread.notifsQueue)
                conn.commit()

                if cursor.rowcount > 0:
                    updatePfsense(ServerThread.cfg, cursor)
                    alert_type = "success"
                    alert_txt = "IP banned successfully"
                else:
                    alert_type = "danger"
                    alert_txt = "Failed to ban IP"

        cursor.execute(
            "SELECT i.idIP, ip FROM ip i INNER JOIN ban b ON (i.idIP = b.idIP) WHERE banned = 1;"
        )
        return render_template(
            "admin.html",
            ips=cursor.fetchall(),
            alert_type=alert_type,
            alert_txt=alert_txt,
        )

    def run(self):
        print("server started")
        self.app.run(host="0.0.0.0", port=8080)

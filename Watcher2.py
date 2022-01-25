import json
import threading
import sqlite3
import random
import re
from sopel import module
from sseclient import SSEClient as EventSource


DB = "wiki.db"


def setup(bot):
    stop_event = threading.Event()
    url = "https://stream.wikimedia.org/v2/stream/recentchange"
    listen = threading.Thread(target=listener, args=(bot, url, stop_event))
    bot.memory["wikistream_stop"] = stop_event
    bot.memory["wikistream_listener"] = listen


def listener(bot, url, stop_event):
    while not stop_event.is_set():
        for event in EventSource(url):
            if stop_event.is_set():
                return
            else:
                if event.event == "message":
                    try:
                        change = json.loads(event.data)
                        dispatch(bot, change)
                    except ValueError:
                        pass


def dispatch(bot, change):
    checklog = checkpage(change)

    if change["type"] == "edit" or change["type"] == "new":
        if checklog["watcher"] is True:
            edit_send(bot, change)

        if checklog["stalk"] is True:
            global_edit(bot, change)

        if re.search(r".*\.css$", change["title"]) or re.search(
            r".*\.js$", change["title"]
        ):
            cssjs(bot, change)

    if checklog["rc_feed"] is True:
        rc_change(bot, change)

    if change["type"] == "log":
        if check_gswiki(change["wiki"]):
            log_send(bot, change)
        if change["log_type"] == "abusefilter":
            af_report(bot, change)


def log_send(bot, change):

    gs = change["user"]
    gs_list = None

    db = sqlite3.connect(DB)
    c = db.cursor()

    try:
        gs_list = c.execute(
            """SELECT account FROM globalsysops WHERE account=?;""", (gs,)
        ).fetchall()
    except:
        pass
    finally:
        db.close()

    report = None

    no_action = [
        "NEWUSERS",
        "RIGHTS",
        "PATROL",
        "REVIEW",
        "ABUSEFILTER",
        "MASSMESSAGE",
        "RENAMEUSER",
        "MOVE",
        "IMPORT",
        "PAGETRANSLATION",
        "THANKS",
    ]

    if len(gs_list) > 0 and gs_list is not None:

        action = str(change["log_type"]).upper()
        pageLink = change["meta"]["uri"]
        space = u"\u200B"
        editor = change["user"][:2] + space + change["user"][2:]
        comment = str(change["comment"]).replace("\n", "")

        if action in no_action:
            return
        elif action == "BLOCK":
            flags = change["log_params"]["flags"]
            duration = change["log_params"]["duration"]
            actionType = change["log_action"]
            report = (
                "Log action: "
                + action
                + " || "
                + editor
                + " "
                + actionType
                + "ed "
                + pageLink
                + " Flags: "
                + flags
                + " Duration: "
                + duration
                + " Comment: "
                + comment[:200]
            )
        elif action == "ABUSEFILTER":
            report = action + " activated by " + editor + " " + pageLink
        elif action == "MOVE":
            report = (
                "Log action: "
                + action
                + " || "
                + editor
                + " moved "
                + pageLink
                + " "
                + comment[:200]
            )
        else:
            report = (
                "Log action: "
                + action
                + " || "
                + editor
                + " "
                + pageLink
                + " "
                + comment[:200]
            )

        if report is not None:
            channel = "#wikimedia-gs-internal"

            if check_hush(channel) is True:
                return
            else:
                bot.say(report, channel)
    else:
        return


def af_report(bot, change):
    project = change["wiki"]

    db = sqlite3.connect(DB)
    c = db.cursor()

    channel = c.execute(
        """SELECT channel FROM af_feed WHERE project=?;""", (project,)
    ).fetchall()

    if len(channel) > 0:

        pageLink = change["meta"]["uri"]
        space = u"\u200B"
        editor = change["user"][:2] + space + change["user"][2:]
        logLink = change["server_url"] + "/wiki/Special:AbuseLog/" + change["log_params"]["log"]
        filterNumber = change["log_params"]["filter"]

        report = "Abuse Filter " + filterNumber + " was activated by " + editor + " at " + pageLink + " " + logLink

        if report is not None:
            for chan in channel:
                if check_hush(chan) is True:
                    return
                else:
                    bot.say(report, chan)


def check_gswiki(project):
    db = sqlite3.connect(DB)
    c = db.cursor()

    check = c.execute(
        """SELECT * FROM GSwikis WHERE project=?;""", (project,)
    ).fetchall()

    db.close()

    if len(check) > 0:
        return True
    else:
        return False


def cssjs(bot, change):
    proj = change["wiki"]
    title = str(change["title"])
    chRev = str(change["revision"]["new"])
    chURL = change["server_url"]
    chDiff = chURL + "/w/index.php?diff=" + chRev + "&safemode=1"
    chComment = change["comment"]
    editor = change["user"]
    space = u"\u200B"
    editor = editor[:2] + space + editor[2:]

    bot.say(
        "\x02"
        + title
        + "\x02 on "
        + proj
        + " was edited by \x02"
        + editor
        + "\x02 "
        + chDiff
        + " "
        + chComment,
        "#wikimedia-cssjs",
    )


def checkpage(change):
    sendLog = {
        "watcher": False,
        "stalk": False,
        "rc_feed": False,
        "af_feed": False
    }

    proj = change["wiki"]

    try:
        nspace, title = str(change["title"]).split(":", 1)
    except ValueError:
        title = str(change["title"])

    db = sqlite3.connect(DB)
    c = db.cursor()

    proj_exists = c.execute(
        """SELECT name FROM sqlite_master WHERE type='table' AND name=?;""", (proj,)
    ).fetchone()
    stalk_exists = c.execute(
        """SELECT title FROM global_watch WHERE title=?;""", (title,)
    ).fetchall()
    RC_exists = c.execute(
        """SELECT * FROM rc_feed WHERE project=?;""", (proj,)
    ).fetchall()
    AF_exists = c.execute(
        """SELECT * FROM af_feed WHERE project=?""", (proj,)
    ).fetchall()

    db.close()

    if len(proj_exists) > 0:
        sendLog["watcher"] = True

    if len(stalk_exists) > 0:
        sendLog["stalk"] = True

    if len(RC_exists) > 0:
        sendLog['rc_feed'] = True

    if len(AF_exists) > 0:
        sendLog['af_feed'] = True

    return sendLog


def global_edit(bot, change):
    """title / namespace / nick / channel / notify"""

    proj = change["wiki"]
    fulltitle = str(change["title"])
    chRev = str(change["revision"]["new"])
    chURL = change["server_url"]
    chDiff = chURL + "/w/index.php?diff=" + chRev
    chComment = change["comment"]
    chNamespace = str(change["namespace"])
    editor = change["user"]
    space = u"\u200B"
    editor = editor[:2] + space + editor[2:]

    try:
        nmspace, title = fulltitle.split(":", 1)
    except ValueError:
        title = fulltitle

    check = None

    db = sqlite3.connect(DB)
    c = db.cursor()

    try:
        check = c.execute(
            """SELECT * FROM global_watch where title=?;""", (title,)
        ).fetchall()
    except:
        return

    if check is not None:
        channels = []

        for record in check:
            (
                target_title,
                target_namespace,
                target_nick,
                target_channel,
                target_notify,
            ) = record
            if target_namespace == chNamespace:
                channels.append(target_channel)
        channels = list(dict.fromkeys(channels))  # Collapse duplicate channels

        for chan in channels:
            nicks = ""
            pgNicks = c.execute(
                """SELECT nick from global_watch where title=? and namespace=? and channel=? and notify='on';""",
                (title, chNamespace, chan)
            ).fetchall()

            if len(pgNicks) > 0:
                for nick in pgNicks:
                    if nicks == "":
                        nicks = nick[0]
                    else:
                        nicks = nick[0] + " " + nicks
                if change["type"] == "edit":
                    newReport = (
                        nicks
                        + ": \x02"
                        + fulltitle
                        + "\x02 on "
                        + proj
                        + " was edited by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )
                elif change["type"] == "create":
                    newReport = (
                        nicks
                        + ": \x02"
                        + fulltitle
                        + "\x02 on "
                        + proj
                        + " was created by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )
            else:
                if change["type"] == "edit":
                    newReport = (
                        "\x02"
                        + fulltitle
                        + "\x02 on "
                        + proj
                        + " was edited by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )
                elif change["type"] == "create":
                    newReport = (
                        "\x02"
                        + fulltitle
                        + "\x02 on "
                        + proj
                        + " was created by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )

            if check_hush(chan) is True:
                continue
            else:
                bot.say(newReport, chan)

        db.close()
    else:
        db.close()


def edit_send(bot, change):

    proj = change["wiki"]
    title = str(change["title"])
    chRev = str(change["revision"]["new"])
    chURL = change["server_url"]
    chDiff = chURL + "/w/index.php?diff=" + chRev
    chComment = change["comment"]
    editor = change["user"]
    space = u"\u200B"
    editor = editor[:2] + space + editor[2:]
    check = None

    db = sqlite3.connect(DB)
    c = db.cursor()

    try:
        check = c.execute(
            """SELECT * FROM ? where page=?;""", (proj, title,)
        ).fetchall()
    except:
        return

    if check is not None:
        channels = []

        for record in check:
            dbPage, dbNick, dbChan, notify = record
            channels.append(dbChan)
        channels = list(dict.fromkeys(channels))  # Collapse duplicate channels

        for chan in channels:
            nicks = ""
            pgNicks = c.execute(
                """SELECT nick from ? where page=? and channel=? and notify='on';""",
                (proj, title, chan,)
            ).fetchall()

            if len(pgNicks) > 0:
                for nick in pgNicks:
                    if nicks == "":
                        nicks = nick[0]
                    else:
                        nicks = nick[0] + " " + nicks
                if change["type"] == "edit":
                    newReport = (
                        nicks
                        + ": \x02"
                        + title
                        + "\x02 on "
                        + proj
                        + " was edited by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )
                elif change["type"] == "create":
                    newReport = (
                        nicks
                        + ": \x02"
                        + title
                        + "\x02 on "
                        + proj
                        + " was created by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )
            else:
                if change["type"] == "edit":
                    newReport = (
                        "\x02"
                        + title
                        + "\x02 on "
                        + proj
                        + " was edited by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )
                elif change["type"] == "create":
                    newReport = (
                        "\x02"
                        + title
                        + "\x02 on "
                        + proj
                        + " was created by \x02"
                        + editor
                        + "\x02 "
                        + chDiff
                        + " "
                        + chComment
                    )

            if check_hush(chan) is True:
                continue
            else:
                bot.say(newReport, chan)

        db.close()
    else:
        db.close()


def check_hush(channel):
    db = sqlite3.connect(DB)
    c = db.cursor()

    hushCheck = c.execute(
        """SELECT * FROM hushchannels WHERE channel=?;""", (channel,)
    ).fetchall()

    db.close()

    if len(hushCheck) > 0:
        return True
    else:
        return False


def watcherAdd(msg, nick, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, project, page = msg.split(" ", 2)

    checkTable = c.execute(
        """SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?;""", (project,)
    ).fetchone()
    if checkTable[0] == 0:
        try:
            c.execute(
                """CREATE TABLE ? (page TEXT, nick TEXT, channel TEXT, notify TEXT);""",
                (project,)
            )
            db.commit()
        except Exception as e:
            response = (
                "Ugh... Something blew up creating the table. Operator873 help me. "
                + str(e)
            )
            db.close()
            return response

        # Check to see if we have the table
        check = c.execute(
            """SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?;""", (project,)
        ).fetchone()
        if check[0] == 0:
            response = (
                "Ugh... Something blew up finding the new table: ("
                + check
                + ") Operator873 help me."
            )
            db.close()
            return response

    pageExists = c.execute(
        """SELECT * from ? WHERE page=? AND nick=? AND channel=?;""",
        (project, page, nick, chan,)
    ).fetchone()
    if pageExists is None:
        try:
            c.execute(
                """INSERT INTO ? VALUES(?, ?, ?, 'off');""",
                (project, page, nick, chan,)
            )
            db.commit()
        except Exception as e:
            response = (
                "Ugh... Something blew up adding the page to the table: "
                + str(e)
                + ". Operator873 help me."
            )
            db.close()
            return response
        check = c.execute(
            """SELECT * FROM ? WHERE page=? AND nick=? AND channel=?;""",
            (project, page, nick, chan,)
        ).fetchone()
        rePage, reNick, reChan, reNotify = check
        response = (
            nick
            + ": I will report changes to "
            + page
            + " on "
            + project
            + " with no ping."
        )
    else:
        response = (
            nick
            + ": you are already watching "
            + page
            + " on "
            + project
            + " in this channel."
        )

    db.close()
    return response


def watcherDel(msg, nick, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, project, page = msg.split(" ", 2)

    checkPage = c.execute(
        """SELECT * FROM ? WHERE page=? AND nick=? AND channel=?;""",
        (project, page, nick, chan,)
    ).fetchone()
    if checkPage is not None:
        try:
            c.execute(
                """DELETE FROM ? WHERE page=? AND nick=? AND channel=?;""",
                (project, page, nick, chan,)
            )
            db.commit()
            response = (
                "%s: I will no longer report changes to %s on %s in this channel for you"
                % (nick, page, project)
            )
        except:
            response = "Ugh... Something blew up. Operator873 help me."
    else:
        response = (
            "%s: it doesn't look like I'm reporting changes to %s on %s in this channel for you."
            % (nick, page, project)
        )

    db.close()
    return response


def watcherPing(msg, nick, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, switch, project, page = msg.split(" ", 3)

    if switch.lower() == "on" or switch.lower() == "off":
        c.execute(
            """UPDATE ? set notify=? where page=? and nick=? and channel=?;""",
            (project, switch, page, nick, chan)
        )
        db.commit()
        response = (
            "Ping set to "
            + switch
            + " for "
            + page
            + " on "
            + project
            + " in this channel."
        )
    else:
        response = (
            "Malformed command! Try: !watch ping {on/off} project The page you want"
        )

    db.close()

    return response


def watcherList(nick, chan):
    response = {
        "result": False,
        "data": []
    }

    db = sqlite3.connect(DB)
    c = db.cursor()

    pages = c.execute('''SELECT ''')



def globalWatcherAdd(msg, nick, chan):
    # !globalwatch add namespaceid title
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, nspace, title = msg.split(" ", 2)

    checkExisting = c.execute(
        """SELECT * FROM global_watch WHERE title=? AND namespace=? AND nick=? AND channel=?;""",
        (title, nspace, nick, chan),
    ).fetchone()

    if checkExisting is None:
        try:
            c.execute(
                """INSERT INTO global_watch VALUES(?, ?, ?, ?, ?);""",
                (title, nspace, nick, chan, "off"),
            )
            db.commit()
        except Exception as e:
            response = (
                "Ugh... Something blew up adding the page to the table: "
                + str(e)
                + ". Operator873 help me."
            )
            db.close()
            return response
        check = c.execute(
            """SELECT * FROM global_watch WHERE title=? AND namespace=? AND nick=? AND channel=?;""",
            (title, nspace, nick, chan),
        ).fetchone()

        page, space, user, channel, ping = check

        response = (
            user
            + ": I will report changes to "
            + page
            + " in namespace "
            + space
            + " on all projects with no ping."
        )
    else:
        response = (
            nick
            + ": you are already globally watching "
            + nspace
            + ":"
            + title
            + " in this channel."
        )

    db.close()
    return response


def globalWatcherDel(msg, nick, chan):
    # !globalwatch del namespaceid title
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, nspace, title = msg.split(" ", 2)

    checkExisting = c.execute(
        """SELECT * FROM global_watch WHERE title=? AND namespace=? AND nick=? AND channel=?;""",
        (title, nspace, nick, chan),
    ).fetchone()

    if checkExisting is not None:
        try:
            c.execute(
                """DELETE FROM global_watch WHERE title=? AND namespace=? AND nick=? AND channel=?;""",
                (title, nspace, nick, chan),
            )
            db.commit()
        except Exception as e:
            response = str(e)
            db.close()
            return response

        check = c.execute(
            """SELECT * FROM global_watch WHERE title=? AND namespace=? AND nick=? AND channel=?;""",
            (title, nspace, nick, chan),
        ).fetchone()

        if check is None:
            response = (
                nick
                + ": I will no longer report changes to "
                + title
                + " in namespace "
                + nspace
                + "."
            )
        else:
            response = "Confirmation failed. Pinging Operator873"
    else:
        response = (
            nick
            + ": you are not globally watching "
            + nspace
            + ":"
            + title
            + " in this channel."
        )

    db.close()
    return response


def globalWatcherPing(msg, nick, chan):
    # !globalwatch ping on namespaceid title
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, switch, nspace, title = msg.split(" ", 3)
    switch = switch.lower()

    if switch == "on" or switch == "off":
        c.execute(
            """UPDATE global_watch SET notify=? WHERE title=? AND namespace=? AND nick=? AND channel=?;""",
            (switch, title, nspace, nick, chan),
        ).fetchone()
        db.commit()
        response = (
            "Ping set to "
            + switch
            + " for "
            + title
            + " in namespace "
            + nspace
            + " in this channel."
        )
    else:
        response = "Malformed command! Try: !globalwatch ping {on/off} namespaceID The page you want"

    db.close()

    return response


@module.commands("speak")
def watcherSpeak(bot, trigger):
    db = sqlite3.connect(DB)
    c = db.cursor()

    doesExist = c.execute(
        """SELECT * FROM hushchannels WHERE channel=?;""", (trigger.sender,)
    ).fetchall()

    if len(doesExist) > 0:
        try:
            if (
                trigger.nick in
                c.execute(
                    """SELECT nick from feed_admins where channel=?;""", (trigger.sender,)
                ).fetchall()
            ):
                c.execute(
                    """DELETE FROM hushchannels WHERE channel=?;""", (trigger.sender)
                )
                db.commit()
                bot.say("Alright! Back to business.")
            else:
                bot.say("You're not authorized to execute this command.")
        except:
            bot.say("Ugh... something blew up. Help me Operator873")
        finally:
            db.close()
    else:
        bot.say(trigger.nick + ": I'm already in 'speak' mode.")


@module.commands("hush")
@module.commands("mute")
def watcherHush(bot, trigger):

    db = sqlite3.connect(DB)
    c = db.cursor()

    import time

    now = time.time()
    timestamp = time.ctime(now)

    doesExist = c.execute(
        """SELECT * FROM hushchannels WHERE channel=?;""", (trigger.sender,)
    ).fetchall()

    if len(doesExist) > 0:
        chan, nick, time = doesExist[0]
        bot.say(
            trigger.nick + ": I'm already hushed by " + nick + " since " + time + "."
        )
        db.close()
    else:
        if (
            trigger.sender == "#wikimedia-gs-internal"
            or trigger.sender == "#wikimedia-gs"
            or trigger.sender == "##OperTestBed"
        ):
            isGS = c.execute(
                """SELECT account from globalsysops where nick=?;""", (trigger.nick,)
            ).fetchall()
            if len(isGS) > 0:
                try:
                    c.execute(
                        """INSERT INTO hushchannels VALUES(?, ?, ?);""",
                        (trigger.sender, trigger.nick, timestamp,)
                    )
                    db.commit()
                    check = c.execute(
                        """SELECT * FROM hushchannels WHERE channel=?;""",
                        (trigger.sender,)
                    ).fetchall()[0]
                    chan, nick, time = check
                    bot.say(nick + " hushed! " + time)
                    db.close()
                except:
                    bot.say("Ugh... something blew up. Help me Operator873")

        elif (
            trigger.nick in
            c.execute(
                """SELECT nick from feed_admins where channel=?;""", (trigger.sender,)
            ).fetchall()
        ):
            try:
                c.execute(
                    """INSERT INTO hushchannels VALUES(?, ?, ?);""",
                    (trigger.sender, trigger.nick, timestamp)
                )
                db.commit()
                check = c.execute(
                    """SELECT * FROM hushchannels WHERE channel=?;""",
                    (trigger.sender,)
                ).fetchall()[0]
                chan, nick, time = check
                bot.say(nick + " hushed! " + time)
                db.close()
            except:
                bot.say("Ugh... something blew up. Help me Operator873")

        else:
            bot.say("You're not authorized to execute this command.")


@module.require_admin(
    message="This function is only available to Operator873 and bot admins."
)
@module.commands("watchstart")
def start_listener(bot, trigger):
    if "wikistream_listener" not in bot.memory:
        stop_event = threading.Event()
        bot.memory["wikistream_stop"] = stop_event
        url = "https://stream.wikimedia.org/v2/stream/recentchange"
        listen = threading.Thread(
            target=listener, args=(bot, url, bot.memory["wikistream_stop"])
        )
        bot.memory["wikistream_listener"] = listen
    bot.memory["wikistream_listener"].start()
    bot.say("Listening to EventStream...")


@module.interval(120)
def checkListener(bot):
    if bot.memory["wikistream_listener"].is_alive() is not True:
        del bot.memory["wikistream_listener"]
        del bot.memory["wikistream_stop"]

        stop_event = threading.Event()
        bot.memory["wikistream_stop"] = stop_event
        url = "https://stream.wikimedia.org/v2/stream/recentchange"

        listen = threading.Thread(
            target=listener, args=(bot, url, bot.memory["wikistream_stop"])
        )

        bot.memory["wikistream_listener"] = listen
        bot.memory["wikistream_listener"].start()
        # bot.say("Restarted listener", "Operator873")
    else:
        pass


@module.require_admin(
    message="This function is only available to Operator873 and bot admins."
)
@module.commands("watchstatus")
def watchStatus(bot, trigger):
    if (
        "wikistream_listener" in bot.memory
        and bot.memory["wikistream_listener"].is_alive() is True
    ):
        msg = "Listener is alive."
    else:
        msg = "Listener is dead."

    bot.say(msg)


@module.require_admin(
    message="This function is only available to Operator873 and bot admins."
)
@module.commands("watchstop")
def watchStop(bot, trigger):
    if "wikistream_listener" not in bot.memory:
        bot.say("Listener isn't running.")
    else:
        try:
            bot.memory["wikistream_stop"].set()
            del bot.memory["wikistream_listener"]
            bot.say("Listener stopped.")
        except Exception as e:
            bot.say(str(e))


@module.require_admin(
    message="This function is only available to Operator873 and bot admins."
)
@module.commands("addmember")
def addGS(bot, trigger):
    db = sqlite3.connect(DB)
    c = db.cursor()
    c.execute(
        """INSERT INTO globalsysops VALUES(?, ?);""",
        (trigger.group(3), trigger.group(4),)
    )
    db.commit()
    nickCheck = c.execute(
        """SELECT nick FROM globalsysops where account=?;""", (trigger.group(4),)
    ).fetchall()
    nicks = ""
    for nick in nickCheck:
        if nicks == "":
            nicks = nick[0]
        else:
            nicks = nicks + " " + nick[0]
    db.close()
    bot.say(
        "Wikipedia account "
        + trigger.group(4)
        + " is now known by IRC nick(s): "
        + nicks
    )


@module.require_admin(
    message="This function is only available to Operator873 and bot admins."
)
@module.commands("removemember")
def delGS(bot, trigger):
    db = sqlite3.connect(DB)
    c = db.cursor()
    c.execute("""DELETE FROM globalsysops WHERE account=?;""", (trigger.group(3)),)
    db.commit()
    checkWork = None
    try:
        checkWork = c.execute(
            """SELECT nick FROM globalsysops WHERE account=?;""", (trigger.group(3),)
        ).fetchall()
        bot.say("All nicks for " + trigger.group(3) + " have been purged.")
    except:
        bot.say("Ugh... Something blew up. Help me Operator873.")


@module.require_chanmsg(message="This message must be used in the channel")
@module.commands("watch")
def watch(bot, trigger):
    watchAction = trigger.group(3)
    if watchAction == "add" or watchAction == "Add" or watchAction == "+":
        if trigger.group(5) == "":
            bot.say("Command seems malformed. Syntax: !watch add proj page")
        else:
            bot.say(watcherAdd(trigger.group(2), trigger.account, trigger.sender))
    elif watchAction == "del" or watchAction == "Del" or watchAction == "-":
        if trigger.group(5) == "":
            bot.say("Command seems malformed. Syntax: !watch del proj page")
        else:
            bot.say(watcherDel(trigger.group(2), trigger.account, trigger.sender))
    elif watchAction == "ping" or watchAction == "Ping":
        if trigger.group(6) == "":
            bot.say("Command seems malformed. Syntax: !watch ping <on/off> proj page")
        else:
            bot.say(watcherPing(trigger.group(2), trigger.account, trigger.sender))
    else:
        bot.say("I don't recognzie that command. Options are: Add & Del")


# !globalwatch ping on namespaceid title
# !globalwatch add namespaceid title
@module.require_chanmsg(message="This message must be used in the channel")
@module.commands("globalwatch")
def gwatch(bot, trigger):
    watchAction = trigger.group(3)
    if watchAction == "add" or watchAction == "Add" or watchAction == "+":
        if trigger.group(5) == "" or trigger.group(5) is None:
            bot.say(
                "Command seems malformed. Syntax: !globalwatch add namespaceID page"
            )
        else:
            bot.say(globalWatcherAdd(trigger.group(2), trigger.account, trigger.sender))
    elif watchAction == "del" or watchAction == "Del" or watchAction == "-":
        if trigger.group(5) == "" or trigger.group(5) is None:
            bot.say(
                "Command seems malformed. Syntax: !globalwatch del namespaceID page"
            )
        else:
            bot.say(globalWatcherDel(trigger.group(2), trigger.account, trigger.sender))
    elif watchAction == "ping" or watchAction == "Ping":
        if trigger.group(6) == "" or trigger.group(6) is None:
            bot.say(
                "Command seems malformed. Syntax: !watch ping <on/off> namespaceID page"
            )
        else:
            bot.say(
                globalWatcherPing(trigger.group(2), trigger.account, trigger.sender)
            )
    else:
        bot.say("I don't recognize that command. Options are: add, del, & ping")


@module.require_chanmsg(message="This message must be used in the channel")
@module.commands("namespace")
def namespaces(bot, trigger):
    listSpaces = {
        "0": "Article",
        "1": "Article talk",
        "2": "User",
        "3": "User talk",
        "4": "Wikipedia",
        "5": "Wikipedia talk",
        "6": "File",
        "7": "File talk",
        "8": "MediaWiki",
        "9": "MediaWiki talk",
        "10": "Template",
        "11": "Template talk",
        "12": "Help",
        "13": "Help talk",
        "14": "Category",
        "15": "Category talk",
        "101": "Portal",
        "102": "Portal talk",
        "118": "Draft",
        "119": "Draft talk",
        "710": "TimedText",
        "711": "TimedText talk",
        "828": "Module",
        "829": "Module talk",
        "2300": "Gadget",
        "2301": "Gadget talk",
    }
    search = trigger.group(2)
    response = ""

    if search == "" or search is None:
        bot.say("Randomly showing an example. Try '!namespace User' or '!namespace 10'")
        num, space = random.choice(list(listSpaces.items()))
        bot.say(num + " is " + space)
    else:
        for item in listSpaces:
            if listSpaces[item].lower() == search.lower():
                response = item
            elif item == search:
                response = listSpaces[item]

        if response == "":
            bot.say(
                "I can't find that name space. Global watch should still work, I just can't provide an example."
            )
        else:
            bot.say(response)

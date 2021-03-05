import json
import threading
import sqlite3
import requests
from sopel import module
from sseclient import SSEClient as EventSource


DB = '/home/ubuntu/.sopel/modules/wiki.db'


def setup(bot):
    stop_event = threading.Event()
    url = "https://stream.wikimedia.org/v2/stream/recentchange"
    listen = threading.Thread(target=listener, args=(bot, url, stop_event))
    bot.memory['wikistream_stop'] = stop_event
    bot.memory['wikistream_listener'] = listen


def listener(bot, url, stop_event):
    while not stop_event.is_set():
        for event in EventSource(url):
            if stop_event.is_set():
                return
            else:
                if event.event == 'message':
                    try:
                        change = json.loads(event.data)
                        dispatch(bot, change)
                    except ValueError:
                        pass


def dispatch(bot, change):

    if change['type'] == 'log':
        if check_gswiki(change['wiki']):
            log_send(bot, change)
    elif change['type'] == 'edit':
        edit_send(bot, change)
    else:
        pass


def log_send(bot, change):

    gs = change['user']
    gs_list = None

    db = sqlite3.connect(DB)
    c = db.cursor()

    try:
        gs_list = c.execute(
            '''SELECT account FROM globalsysops WHERE account="%s";''' % gs
        ).fetchall()
    except:
        pass
    finally:
        db.close()

    report = None

    no_action = [
        'NEWUSERS',
        'RIGHTS',
        'PATROL',
        'REVIEW',
        'ABUSEFILTER',
        'MASSMESSAGE',
        "RENAMEUSER",
        "MOVE",
        "IMPORT",
        "PAGETRANSLATION"
    ]

    if len(gs_list) > 0 and gs_list is not None:

        action = str(change['log_type']).upper()
        pageLink = change['meta']['uri']
        space = u'\u200B'
        editor = change['user'][:2] + space + change['user'][2:]
        comment = str(change['comment']).replace('\n', '')

        if action in no_action:
            return
        elif action == "BLOCK":
            flags = change['log_params']['flags']
            duration = change['log_params']['duration']
            actionType = change['log_action']
            report = "Log action: " + action + " || " + editor + " " + actionType + "ed " + pageLink + " Flags: " + flags + " Duration: " + duration + " Comment: " + comment[
                                                                                                                                                                      :200]
        elif action == "ABUSEFILTER":
            report = action + " activated by " + editor + " " + pageLink
        elif action == "MOVE":
            report = "Log action: " + action + " || " + editor + " moved " + pageLink + " " + comment[:200]
        else:
            report = "Log action: " + action + " || " + editor + " " + pageLink + " " + comment[:200]

        if report is not None:
            channel = "#wikimedia-gs-internal"

            if check_hush(channel) is True:
                return
            else:
                bot.say(report, channel)
    else:
        return


def check_global_page(bot, change):
    try:
        notused_namespace, chk_title = change['title'].split(':', 1)
    except ValueError:
        return

    check = None

    db = sqlite3.connect(DB)
    c = db.cursor()

    try:
        check = c.execute('''SELECT * FROM global_watch where title="%s" and namespace="%s";''' % (chk_title, change['namespace'])).fetchall()
    except:
        db.close()
        return

    if check is not None:
        title = change['title']
        proj = change['wiki']
        chRev = str(change['revision']['new'])
        chURL = change['server_url']
        chDiff = chURL + "/w/index.php?diff=" + chRev
        chComment = change['comment']
        editor = change['user']
        space = u'\u200B'
        editor = editor[:2] + space + editor[2:]

        channels = []

        for record in check:
            dbPage, dbNamespace, dbNick, dbChan, notify = record
            channels.append(dbChan)
        channels = list(dict.fromkeys(channels))  # Collapse duplicate channels

        for chan in channels:
            nicks = ""
            pgNicks = c.execute('SELECT nick from global_watch where title="%s" and channel="%s" and notify="on";' % (
                title, chan)).fetchall()

            if len(pgNicks) > 0:
                for nick in pgNicks:
                    if nicks == "":
                        nicks = nick[0]
                    else:
                        nicks = nick[0] + " " + nicks
                newReport = nicks + ": \x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment
            else:
                newReport = "\x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment

            if check_hush(chan) is True:
                continue
            else:
                bot.say(newReport, chan)
        db.close()
    else:
        db.close()

def edit_send(bot, change):

    proj = change['wiki']
    title = str(change['title'])
    chRev = str(change['revision']['new'])
    chURL = change['server_url']
    chDiff = chURL + "/w/index.php?diff=" + chRev
    chComment = change['comment']
    editor = change['user']
    space = u'\u200B'
    editor = editor[:2] + space + editor[2:]
    check = None

    if ':' in change['title']:
        check_global_page(bot, change)

    db = sqlite3.connect(DB)
    c = db.cursor()

    try:
        check = c.execute('''SELECT * FROM %s where page="%s";''' % (proj, title)).fetchall()
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
            pgNicks = c.execute('SELECT nick from %s where page="%s" and channel="%s" and notify="on";' % (
                proj, title, chan)).fetchall()

            if len(pgNicks) > 0:
                for nick in pgNicks:
                    if nicks == "":
                        nicks = nick[0]
                    else:
                        nicks = nick[0] + " " + nicks
                newReport = nicks + ": \x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment
            else:
                newReport = "\x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment

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
        '''SELECT * FROM hushchannels WHERE channel="%s";''' % channel
    ).fetchall()

    db.close()

    if len(hushCheck) > 0:
        return True
    else:
        return False


def check_gswiki(project):
    db = sqlite3.connect(DB)
    c = db.cursor()

    check = c.execute('''SELECT * FROM GSwikis WHERE project="%s";''' % project).fetchall()

    db.close()

    if len(check) > 0:
        return True
    else:
        return False



def watcherAdd(msg, nick, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, project, page = msg.split(' ', 2)

    checkTable = c.execute(
        '''SELECT count(*) FROM sqlite_master WHERE type="table" AND name="%s";''' % project).fetchone()
    if checkTable[0] == 0:
        try:
            c.execute('''CREATE TABLE %s (page TEXT, nick TEXT, channel TEXT, notify TEXT);''' % project)
            db.commit()
        except Exception as e:
            response = "Ugh... Something blew up creating the table. Operator873 help me. " + str(e)
            db.close()
            return response

        # Check to see if we have the table
        check = c.execute(
            '''SELECT count(*) FROM sqlite_master WHERE type="table" AND name="%s";''' % project).fetchone()
        if check[0] == 0:
            response = "Ugh... Something blew up finding the new table: (" + check + ") Operator873 help me."
            db.close()
            return response

    pageExists = c.execute(
        '''SELECT * from %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan)).fetchone()
    if pageExists is None:
        try:
            c.execute('''INSERT INTO %s VALUES("%s", "%s", "%s", "off");''' % (project, page, nick, chan))
            db.commit()
        except Exception as e:
            response = "Ugh... Something blew up adding the page to the table: " + str(e) + ". Operator873 help me."
            db.close()
            return response
        check = c.execute('''SELECT * FROM %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (
        project, page, nick, chan)).fetchone()
        rePage, reNick, reChan, reNotify = check
        response = nick + ": I will report changes to " + page + " on " + project + " with no ping."
    else:
        response = nick + ": you are already watching " + page + " on " + project + " in this channel."

    db.close()
    return response


def watcherDel(msg, nick, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, project, page = msg.split(' ', 2)

    checkPage = c.execute(
        '''SELECT * FROM %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan)).fetchone()
    if checkPage is not None:
        try:
            c.execute(
                '''DELETE FROM %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan))
            db.commit()
            response = "%s: I will no longer report changes to %s on %s in this channel for you" % (nick, page, project)
        except:
            response = "Ugh... Something blew up. Operator873 help me."
    else:
        response = "%s: it doesn't look like I'm reporting changes to %s on %s in this channel for you." % (
        nick, page, project)

    db.close()
    return response

def watcherPing(msg, nick, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    action, switch, project, page = msg.split(' ', 3)

    if switch == "on" or switch == "On" or switch == "off" or switch == "Off":
        c.execute('''UPDATE %s set notify="%s" where page="%s" and nick="%s" and channel="%s";''' % (
        project, switch, page, nick, chan))
        db.commit()
        response = "Ping set to " + switch + " for " + page + " on " + project + " in this channel."
    else:
        response = "Malformed command! Try: !watch ping {on/off} project The page you want"

    db.close()

    return response

def global_watch_add(name, command, chan):

    db = sqlite3.connect(DB)
    c = db.cursor()

    switch, action, namespace, page = command.split(' ', 3)

    pageExists = c.execute(
        '''SELECT * from global_watch WHERE title="%s" AND nick="%s" AND channel="%s" AND namespace="%s";''' % (page, name, chan, str(namespace))).fetchone()
    if pageExists is None:
        try:
            c.execute('''INSERT INTO global_watch VALUES("%s", "%s", "%s", "%s", "off");''' % (page, str(namespace), name, chan))
            db.commit()
        except Exception as e:
            response = "Ugh... Something blew up adding the page to the table: " + str(e) + ". Operator873 help me."
            db.close()
            return response
        check = c.execute('''SELECT * FROM global_watch WHERE title="%s" AND nick="%s" AND channel="%s" AND namespace="%s";''' % (
            page, name, chan, namespace)).fetchone()
        reTitle, reNamespace, reNick, reChan, reNotify = check
        response = name + ": I will report changes to " + reTitle + " in namespace " + str(reNamespace) + " with no ping."
    else:
        response = name + ": you are already watching " + reTitle + " in namespace " + str(reNamespace) + " in this channel."

    db.close()
    return response

def global_watch_del(name, command, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    switch, action, namespace, page = command.split(' ', 3)

    checkPage = c.execute(
        '''SELECT * FROM global_watch WHERE title="%s" AND nick="%s" AND channel="%s" AND namespace="%s";''' % (page, name, chan, str(namespace))).fetchone()
    if checkPage is not None:
        try:
            c.execute(
                '''DELETE FROM global_watch WHERE title="%s" AND nick="%s" AND channel="%s" AND namespace="%s";''' % (page, name, chan, str(namespace)))
            db.commit()
            response = "%s: I will no longer report changes to %s in namespace %s in this channel for you" % (name, page, str(namespace))
        except:
            response = "Ugh... Something blew up. Operator873 help me. (line 396)"
    else:
        response = "%s: it doesn't look like I'm reporting changes to %s in namespace '%s' in this channel for you." % (
            name, page, str(namespace))

    db.close()
    return response


def global_watch_ping(name, command, chan):
    db = sqlite3.connect(DB)
    c = db.cursor()

    g, p, switch, namespace, title = command.split(' ', 4)

    if switch.lower() == "on" or switch.lower() == "off":
        c.execute('''UPDATE global_watch set notify="%s" where title="%s" and nick="%s" and channel="%s" and namespace="%s";''' % (
            switch.lower(), title, name, chan, str(namespace)))
        db.commit()
        response = "Ping set to " + switch.lower() + " for " + title + " in namespace '" + str(namespace) + "' in this channel."
    else:
        response = "Malformed command! Try: !watch global help"

    db.close()

    return response

@module.commands('speak')
def watcherSpeak(bot, trigger):
    db = sqlite3.connect(DB)
    c = db.cursor()

    doesExist = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % trigger.sender).fetchall()

    if len(doesExist) > 0:
        try:
            c.execute('''DELETE FROM hushchannels WHERE channel="%s";''' % trigger.sender)
            db.commit()
            bot.say("Alright! Back to business.")
        except:
            bot.say("Ugh... something blew up. Help me Operator873")
        finally:
            db.close()
    else:
        bot.say(trigger.nick + ": I'm already in 'speak' mode.")


@module.commands('hush')
@module.commands('mute')
def watcherHush(bot, trigger):

    db = sqlite3.connect(DB)
    c = db.cursor()

    import time
    now = time.time()
    timestamp = time.ctime(now)

    doesExist = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % trigger.sender).fetchall()

    if len(doesExist) > 0:
        chan, nick, time = doesExist[0]
        bot.say(trigger.nick + ": I'm already hushed by " + nick + " since " + time + ".")
        db.close()
    else:
        if trigger.sender == "#wikimedia-gs-internal" or trigger.sender == "#wikimedia-gs" or trigger.sender == "##OperTestBed":
            isGS = c.execute('''SELECT account from globalsysops where nick="%s";''' % trigger.nick).fetchall()
            if len(isGS) > 0:
                try:
                    c.execute('''INSERT INTO hushchannels VALUES("%s", "%s", "%s");''' % (
                    trigger.sender, trigger.nick, timestamp))
                    db.commit()
                    check = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % trigger.sender).fetchall()[
                        0]
                    chan, nick, time = check
                    bot.say(nick + " hushed! " + time)
                    db.close()
                except:
                    bot.say("Ugh... something blew up. Help me Operator873")

        else:
            try:
                c.execute('''INSERT INTO hushchannels VALUES("%s", "%s", "%s");''' % (
                trigger.sender, trigger.nick, timestamp))
                db.commit()
            except:
                bot.say("Ugh... something blew up. Help me Operator873")
            finally:
                check = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % trigger.sender).fetchall()[0]
                chan, nick, time = check
                bot.say(nick + " hushed! " + time)
                db.close()


@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('watchstart')
def start_listener(bot, trigger):
    if 'wikistream_listener' not in bot.memory:
        stop_event = threading.Event()
        bot.memory['wikistream_stop'] = stop_event
        url = "https://stream.wikimedia.org/v2/stream/recentchange"
        listen = threading.Thread(target=listener, args=(bot, url, bot.memory['wikistream_stop']))
        bot.memory['wikistream_listener'] = listen
    bot.memory['wikistream_listener'].start()
    bot.say('Listening to EventStream...')


@module.interval(120)
def checkListener(bot):
    if bot.memory['wikistream_listener'].is_alive() is not True:
        bot.memory['wikistream_listener'].join()
        del bot.memory['wikistream_listener']
        del bot.memory['wikistream_stop']

        stop_event = threading.Event()
        bot.memory['wikistream_stop'] = stop_event
        url = "https://stream.wikimedia.org/v2/stream/recentchange"

        listen = threading.Thread(target=listener, args=(bot, url, bot.memory['wikistream_stop']))

        bot.memory['wikistream_listener'] = listen
        bot.memory['wikistream_listener'].start()
        # bot.say("Restarted listener", "Operator873")
    else:
        pass


@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('watchstatus')
def watchStatus(bot, trigger):
    if 'wikistream_listener' in bot.memory and bot.memory['wikistream_listener'].is_alive() is True:
        msg = "Listener is alive."
    else:
        msg = "Listener is dead."

    bot.say(msg)


@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('watchstop')
def watchStop(bot, trigger):
    if 'wikistream_listener' not in bot.memory:
        bot.say("Listener isn't running.")
    else:
        try:
            bot.memory['wikistream_stop'].set()
            del bot.memory['wikistream_listener']
            bot.say("Listener stopped.")
        except Exception as e:
            bot.say(str(e))


@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('addmember')
def addGS(bot, trigger):
    db = sqlite3.connect(DB)
    c = db.cursor()
    c.execute('''INSERT INTO globalsysops VALUES("%s", "%s");''' % (trigger.group(3), trigger.group(4)))
    db.commit()
    nickCheck = c.execute('''SELECT nick FROM globalsysops where account="%s";''' % trigger.group(4)).fetchall()
    nicks = ""
    for nick in nickCheck:
        if nicks == "":
            nicks = nick[0]
        else:
            nicks = nicks + " " + nick[0]
    db.close()
    bot.say("Wikipedia account " + trigger.group(4) + " is now known by IRC nick(s): " + nicks)


@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('removemember')
def delGS(bot, trigger):
    db = sqlite3.connect(DB)
    c = db.cursor()
    c.execute('''DELETE FROM globalsysops WHERE account="%s";''' % trigger.group(3))
    db.commit()
    checkWork = None
    try:
        checkWork = c.execute('''SELECT nick FROM globalsysops WHERE account="%s";''' % trigger.group(3)).fetchall()
        bot.say("All nicks for " + trigger.group(3) + " have been purged.")
    except:
        bot.say("Ugh... Something blew up. Help me Operator873.")


@module.require_chanmsg(message="This message must be used in the channel")
@module.commands('watch')
def watch(bot, trigger):
    watchAction = trigger.group(3)
    if watchAction.lower() == "add" or watchAction == "+":
        if trigger.group(5) == "":
            bot.say("Command seems malformed. Syntax: !watch add proj page")
        else:
            bot.say(watcherAdd(trigger.group(2), trigger.nick, trigger.sender))
    elif watchAction.lower() == "del" or watchAction == "-":
        if trigger.group(5) == "":
            bot.say("Command seems malformed. Syntax: !watch del proj page")
        else:
            bot.say(watcherDel(trigger.group(2), trigger.nick, trigger.sender))
    elif watchAction.lower() == "ping":
        if trigger.group(6) == "":
            bot.say("Command seems malformed. Syntax: !watch ping <on/off> proj page")
        else:
            bot.say(watcherPing(trigger.group(2), trigger.nick, trigger.sender))
    elif watchAction.lower() == 'global':
        # !watch global help
        # !watch global <add/del> <namespace id> <page>
        # !watch global ping <on/off> <namespace id> <page>
        if trigger.group(4).lower() == 'help':
            bot.say("Command is: !watch global <add/del> <namespace id> <page>")
            bot.say("To turn ping on or off: !watch global ping <on/off> <namespace id> <page>")
            bot.say("See https://enwp.org/WP:NS for namespace IDs (0 Article / Article talk 1)")
        elif trigger.group(4).lower() == 'add' and trigger.group(6) != "":
            bot.say(global_watch_add(trigger.nick, trigger.group(2), trigger.sender))
        elif trigger.group(4).lower() == 'del' and trigger.group(6) != "":
            bot.say(global_watch_del(trigger.nick, trigger.group(2), trigger.sender))
        elif trigger.group(4).lower() == 'ping' and trigger.group(7) != "":
            bot.say(global_watch_ping(trigger.nick, trigger.group(2), trigger.sender))
        else:
            bot.say("Command is: !watch global <add/del> <namespace id> <page>")
            bot.say("To turn ping on or off: !watch global ping <on/off> <namespace id> <page>")
            bot.say("See https://enwp.org/WP:NS for namespace IDs (0 Article / Article talk 1)")
    else:
        bot.say("I don't recognzie that command. Options are: Add, Del, and global")

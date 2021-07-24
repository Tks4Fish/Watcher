import json
import threading
import sqlite3
import requests
import re
from sopel import module
from sseclient import SSEClient as EventSource


DB = '/home/hades/.sopel/modules/wiki.db'


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
    bot.say("Listener stopped", "Operator873")


def dispatch(bot, change):

    if change['type'] == 'edit':
        sendLog = checkpage(change)
        if sendLog['watcher'] is True:
            edit_send(bot, change)

        if sendLog['stalk'] is True:
            global_edit(bot, change)

    if re.search(r'.*\.css$', change['title']) or re.search(r'.*\.js$', change['title']):
        cssjs(bot, change)

def cssjs(bot, change):
    proj = change['wiki']
    title = str(change['title'])
    chRev = str(change['revision']['new'])
    chURL = change['server_url']
    chDiff = chURL + "/w/index.php?diff=" + chRev + '&safemode=1'
    chComment = change['comment']
    editor = change['user']
    space = u'\u200B'
    editor = editor[:2] + space + editor[2:]

    bot.say("\x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment, '#wikimedia-cssjs')


def checkpage(change):
    sendLog = {
        'watcher':False,
        'stalk':False
    }
    proj = change['wiki']
    title = str(change['title'])

    table_query = '''SELECT name FROM sqlite_master WHERE type='table' AND name='{}';'''
    stalk_query = '''SELECT title FROM global_watch WHERE title='{}';'''

    db = sqlite3.connect(DB)
    c = db.cursor()

    proj_exists = c.execute(table_query.format(proj)).fetchone()
    stalk_exists = c.execute(stalk_query.format(title)).fetchone()

    db.close()

    if proj_exists is not None:
        sendLog['watcher'] = True

    if stalk_exists is not None:
        sendLog['stalk'] = True

    return sendLog



def global_edit(bot, change):
    """ title / namespace / nick / channel / notify """

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

    try:
        check = c.execute('''SELECT * FROM global_watch where page="%s";''' % (title)).fetchall()
    except:
        return

    target_title, target_namespace, target_nick, target_channel, target_notify = check



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
    if watchAction == "add" or watchAction == "Add" or watchAction == "+":
        if trigger.group(5) == "":
            bot.say("Command seems misformed. Syntax: !watch add proj page")
        else:
            bot.say(watcherAdd(trigger.group(2), trigger.nick, trigger.sender))
    elif watchAction == "del" or watchAction == "Del" or watchAction == "-":
        if trigger.group(5) == "":
            bot.say("Command seems misformed. Syntax: !watch del proj page")
        else:
            bot.say(watcherDel(trigger.group(2), trigger.nick, trigger.sender))
    elif watchAction == "ping" or watchAction == "Ping":
        if trigger.group(6) == "":
            bot.say("Command seems misformed. Syntax: !watch ping <on/off> proj page")
        else:
            bot.say(watcherPing(trigger.group(2), trigger.nick, trigger.sender))
    else:
        bot.say("I don't recognzie that command. Options are: Add & Del")

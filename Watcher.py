# This is the live version
import time
import json
import threading
import sqlite3
import requests
from sopel import module
from sopel import tools
from sseclient import SSEClient as EventSource

reports = []
with open('/home/ubuntu/.sopel/modules/wikiList.txt', 'r') as f:
    wikiList = f.read().splitlines()

class wiki():
    
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
    data = c.execute('SELECT * from config;').fetchall()[0]
    stream, botAct, botPass, csrf, botNick = data
    
    def checkTable(project):
        # Checks for tables existence. Returns 1 for True and 0 for False and NoneType for error
        try:
            data = wiki.c.execute('''SELECT count(*) FROM sqlite_master WHERE type="table" AND name="%s";''' % project).fetchone()
            return data
        except:
            return None
    
    def createTable(project):
        # Creates a new table... Used after checking with checkTable(project)
        try:
            wiki.c.execute('CREATE TABLE ' + project + '(page TEXT, nick TEXT, channel TEXT, notify TEXT);')
            wiki2.db.commit()
            return True
        except:
            return None
    
    def checkPage(project, title):
        # Check and see if EventStream item needs to be processed
        try:
            check = wiki.c.execute('''SELECT * FROM %s WHERE page="%s";''' % (project, title)).fetchone()
            return check
        except:
            return None
    
    def getPage(project, title):
        # If checkPage(project, title) returned an existing page, get the info to process
        try:
            data = wiki.c.execute('''SELECT * FROM %s WHERE page="%s";''' % (project, title)).fetchall()
            return data
        except:
            return None
    
    def getPageNicks(project, page, chan):
        # While processing getPage(project, title), get the specific nicks we need to notify per channel
        try:
            data = wiki.c.execute('''SELECT nick from %s where page="%s" and channel="%s" and notify="yes";''' % (project, page, chan)).fetchall()
            return data
        except:
            return None
    
    def checkNewPage(project, page, nick, channel):
        try:
            check = wiki.c.execute('''SELECT * from %s where page="%s" and nick="%s" and channel="%s";''' % (project, page, nick, channel)).fetchone()
            return check
        except:
            return None
        
    def createPage(project, page, nick, channel):
        # Add a page to be watched by a nick. Should be used after checking for already watched page
        try:
            notify = "no"
            schema = "INSERT INTO " + project + "(page, nick, channel, notify) VALUES(?,?,?,?);"
            wiki.c.execute(schema, (page, nick, channel, notify))
            wiki2.db.commit()
            return True
        except:
            return None
    
    def setNotify(project, page, nick, channel, notify):
        # Change the notify settings of an entry
        try:
            work = wiki.c.execute('''UPDATE %s set notify="%s" where page="%s" and nick="%s" and channel="%s";''' % (project, notify, page, nick, channel))
            wiki2.db.commit()
            return True
        except:
            return None
    
    def deletePage(project, page, nick, channel):
        try:
            work = wiki.c.execute('''DELETE FROM %s WHERE page="%s" AND channel="%s" AND nick="%s";''' % (project, page, channel, nick))
            wiki2.db.commit()
            return True
        except:
            return None
    
    def listPages(project):
        try:
            data = wiki.c.execute('''SELECT page from %s;''' % project).fetchall()
            return data
        except:
            return None

    def checkSysop(actName):
        # Check to see if a username is in the Global Sysops table. Returns 1 for yes, 0 for no, None for error
        try:
            response = wiki.c.execute('''SELECT account from globalsysops where account="%s";''' % actName).fetchall()
            return response
        except:
            return None

def setup(bot):
    stop_event = threading.Event()
    listen = threading.Thread(target=listener, args=(wiki.stream, stop_event))
    reports = []
    bot.memory['wikistream_stop'] = stop_event
    bot.memory['wikistream_listener'] = listen
    with open('/home/ubuntu/.sopel/modules/wikiList.txt', 'r') as f:
        wikiList = f.read().splitlines()

def logSend(change):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
    editor = change['user']
    GSes = None
    try:
        GSes = c.execute('''SELECT account from globalsysops where account="%s";''' % editor).fetchall()
    except:
        pass
    if len(GSes) > 0 and GSes is not None:
        action = str(change['log_type']).upper()
        pageLink = change['meta']['uri']
        project = change['wiki']
        space = u'\u200B'
        editor = editor[:2] + space + editor[2:]
        title = change['title']
        comment = str(change['comment']).replace('\n','')
        report = None
        if action == "NEWUSERS":
            pass
            #report = "Account created: " + editor + " " + pageLink
        elif action == "BLOCK":
            flags = change['log_params']['flags']
            duration = change['log_params']['duration']
            actionType = change['log_action']
            report = "Log action: " + action + " || " + editor + " " + actionType + "ed " + pageLink + " Flags: " + flags + " Duration: " + duration + " Comment: " + comment[:200]
        elif action == "ABUSEFILTER":
            report = action + " activated by " + editor + " " + pageLink
        elif action == "MOVE":
            report = "Log action: " + action + " || " + editor + " moved " + pageLink + " " + comment[:200]
        elif action == "PATROL" or action == "REVIEW" or action == "THANKS" or action == "UPLOAD" or action == "ABUSEFILTER" or action == "MASSMESSAGE" or action == "RENAMEUSER" or action == "MOVE" or action == "IMPORT":
            pass
        else:
            report = "Log action: " + action + " || " + editor + " " + pageLink + " " + comment[:200]
        if report is not None:
            channel = "#wikimedia-gs-internal"
            hushCheck = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % channel).fetchall()
            if len(hushCheck) > 0:
                return
            else:
                report = channel + " " + report
                reports.append(report)

def editSend(change):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
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
        check = c.execute('''SELECT * FROM %s where page="%s";''' % (proj, title)).fetchall()
    except:
        pass
    if check is not None:
        channels = []
        for record in check:
            dbPage, dbNick, dbChan, notify = record
            channels.append(dbChan)
        channels = list(dict.fromkeys(channels)) # Collapse duplicate channels
        for chan in channels:
            nicks = ""
            pgNicks = c.execute('SELECT nick from %s where page="%s" and channel="%s" and notify="on";' % (proj, title, chan)).fetchall()
            if len(pgNicks) > 0:
                for nick in pgNicks:
                    if nicks == "":
                        nicks = nick[0]
                    else:
                        nicks = nick[0] + " " + nicks
                newReport = chan + " " + nicks + ": \x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment
            else:
                newReport = chan + " \x02" + title + "\x02 on " + proj + " was edited by \x02" + editor + "\x02 " + chDiff + " " + chComment
            hushCheck = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % chan).fetchall()
            if len(hushCheck) > 0:
                continue
            else:
                reports.append(newReport)

def dispatcher(change):
    if change['type'] == "log":
        if change['wiki'] in wikiList:
            logSend(change)
    elif change['type'] == "edit":
        editSend(change)
    else:
        pass

def listener(url, stop_event):
    while not stop_event.is_set():
        for event in EventSource(url):
            if not stop_event.is_set():
                if event.event == 'message':
                    try:
                        change = json.loads(event.data)
                        dispatcher(change)
                    except ValueError:
                        pass
            else:
                return
    lpstop = "Operator873 Listener stopped."
    reports.append(lpstop)

def watcherAdd(msg, nick, chan):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
    action, project, page = msg.split(' ', 2)
    checkTable = c.execute('''SELECT count(*) FROM sqlite_master WHERE type="table" AND name="%s";''' % project).fetchone()
    if checkTable[0] == 0:
        try:
            c.execute('''CREATE TABLE %s (page TEXT, nick TEXT, channel TEXT, notify TEXT);''' % project)
            db.commit()
        except Exception as e:
            response = "Ugh... Something blew up creating the table. Operator873 help me. " + str(e)
            db.close()
            return response
        # Check to see if we have the table
        check = c.execute('''SELECT count(*) FROM sqlite_master WHERE type="table" AND name="%s";''' % project).fetchone()
        if check[0] == 0:
            response = "Ugh... Something blew up finding the new table: (" + check + ") Operator873 help me."
            db.close()
            return response
    pageExists = c.execute('''SELECT * from %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan)).fetchone()
    if pageExists is None:
        try:
            c.execute('''INSERT INTO %s VALUES("%s", "%s", "%s", "off");''' % (project, page, nick, chan))
            db.commit()
        except Exception as e:
            response = "Ugh... Something blew up adding the page to the table: " + str(e) + ". Operator873 help me."
            db.close()
            return response
        check = c.execute('''SELECT * FROM %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan)).fetchone()
        rePage, reNick, reChan, reNotify = check
        response = nick + ": I will report changes to " + page + " on " + project + " with no ping."
        db.close()
        return response
    else:
        response = nick + ": you are already watching " + page + " on " + project + " in this channel."
        db.close()
        return response

def watcherDel(msg, nick, chan):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
    action, project, page = msg.split(' ', 2)
    checkPage = c.execute('''SELECT * FROM %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan)).fetchone()
    if checkPage is not None:
        try:
            c.execute('''DELETE FROM %s WHERE page="%s" AND nick="%s" AND channel="%s";''' % (project, page, nick, chan))
            db.commit()
            response = "%s: I will no longer report changes to %s on %s in this channel for you" % (nick, page, project)
        except:
            response = "Ugh... Something blew up. Operator873 help me."
    else:
        response = "%s: it doesn't look like I'm reporting changes to %s on %s in this channel for you." % (nick, page, project)
    return response
    db.close()

def watcherPing(msg, nick, chan):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
    action, switch, project, page = msg.split(' ', 3)
    readChange = None
    if switch == "on" or switch == "On" or switch == "off" or switch == "Off":
        readChange = c.execute('''UPDATE %s set notify="%s" where page="%s" and nick="%s" and channel="%s";''' % (project, switch, page, nick, chan))
        db.commit()
        response = "Ping set to " + switch + " for " + page + " on " + project + " in this channel."
    else:
        response = "Malformed command! Try: !watch ping {on/off} project The page you want"
    return response

def updateGSwikis():
    with open('/home/ubuntu/.sopel/modules/wikiList.txt', 'w') as repo:
        repo.write("")
    connect = requests.Session()
    checkurl = 'https://meta.wikimedia.org/w/api.php'
    myParams = {
        'format':"json",
        'action':"query",
        'list':"wikisets",
        'wsprop':"wikisincluded",
        'wsfrom':"Opted-out of global sysop wikis"
    }

    agent = {
        'User-Agent': 'Bot873 v0.1 using Python3.7 Sopel',
        'From': 'operator873@873gear.com'
    }
    DATA = connect.get(checkurl, headers=agent, params=myParams).json()
    wikis = DATA['query']['wikisets'][0]
    check = wikis['wikisincluded']
    with open('/home/ubuntu/.sopel/modules/wikiList.txt', 'w') as repo:
        for x in check:
            repo.write('%s\n' % check[x])

def readWikiList():
    count = len(open('/home/ubuntu/.sopel/modules/wikiList.txt', 'r').read().splitlines())
    response = "I am monitoring " + str(count) + " wikis for GS edits."
    return response
        
def checkReporter(bot):
    if len(reports) > 0:
        for item in reversed(reports):
            channel, msg = item.split(' ', 1)
            bot.say(msg, channel)
            reports.remove(item)

@module.commands('speak')
def watcherSpeak(bot, trigger):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
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
    import time
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
    c = db.cursor()
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
                    c.execute('''INSERT INTO hushchannels VALUES("%s", "%s", "%s");''' % (trigger.sender, trigger.nick, timestamp))
                    db.commit()
                    check = c.execute('''SELECT * FROM hushchannels WHERE channel="%s";''' % trigger.sender).fetchall()[0]
                    chan, nick, time = check
                    bot.say(nick + " hushed! " + time)
                    db.close()
                except:
                    bot.say("Ugh... something blew up. Help me Operator873")

        else:
            try:
                c.execute('''INSERT INTO hushchannels VALUES("%s", "%s", "%s");''' % (trigger.sender, trigger.nick, timestamp))
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
        listen = threading.Thread(target=listener, args=(wiki.stream, stop_event))
        bot.memory['wikistream_listener'] = listen
    bot.memory['wikistream_listener'].start()
    bot.say('Listening to EventStream...')

@module.require_owner(message="This function is only available to Operator873.")
@module.commands('readGSwikis')
def readGSwikis(bot, trigger):
    updateGSwikis()
    bot.say("GS wikis have been updated.")

@module.require_owner(message="This function is only available to Operator873.")
@module.commands('readdbrows')
def readdb(bot, trigger):
    proj, page = trigger.group(2).split(' ', 1)
    data = wiki.getPage(proj, page)
    for item in data:
        bot.say(str(item), trigger.sender)

@module.require_owner(message="This function is only available to Operator873.")
@module.commands('readdbtables')
def readdbtable(bot, trigger):
    if wiki.checkTable(trigger.group(3))[0] > 0:
        pages = wiki.listPages(trigger.group(3))
        bot.say("I have a table called " + trigger.group(3) + ". The rows are called: " + str(pages))
    else:
        bot.say("I do not have a table called " + trigger.group(3))

@module.require_owner(message="This function is only available to Operator873.")
@module.commands('getdbpage')
def getdbpage(bot, trigger):
    project, page = trigger.group(2).split(' ', 1)
    if wiki.getPage(project, page):
        bot.say("Yes.")

@module.priority("high")
@module.interval(2)
def checkReports(bot):
    checkReporter(bot)

@module.interval(120)
def checkListener(bot):
    if bot.memory['wikistream_listener'].is_alive() is not True:
        bot.memory['wikistream_listener'].join()
        del bot.memory['wikistream_listener']
        del bot.memory['wikistream_stop']
        stop_event = threading.Event()
        listen = threading.Thread(target=listener, args=(wiki.stream, stop_event))
        bot.memory['wikistream_listener'] = listen
        bot.memory['wikistream_listener'].start()
        bot.memory['wikistream_stop'] = stop_event
        bot.say("Restarted listener", "Operator873")
    else:
        pass

@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('countwikis')
def cmdreadWikilist(bot, trigger):
    bot.say(readWikiList())

@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('watchstatus')
def watchStatus(bot, trigger):
    if 'wikistream_listener' in bot.memory and bot.memory['wikistream_listener'].is_alive() is True:
        msg = trigger.sender + " Reader is functioning. Listener is alive."
    else:
        msg = trigger.sender + " Reader is functioning, but Listener is dead."
    reports.append(msg)

@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('watchstop')
def watchStop(bot, trigger):
    if 'wikistream_listener' not in bot.memory:
        bot.say("Listener isn't running.")
    else:
        try:
            del bot.memory['wikistream_listener']
            bot.say("Listener stopped. Reports container dumped.")
        except Exception as e:
            bot.say(str(e))

@module.require_admin(message="This function is only available to Operator873 and bot admins.")
@module.commands('addmember')
def addGS(bot, trigger):
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
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
    db = sqlite3.connect("/home/ubuntu/.sopel/modules/wiki2.db", check_same_thread=False)
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

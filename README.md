![GitHub All Releases](https://img.shields.io/github/downloads/Operator873/SAM-for-desktop/releases)

# Wikimedia Watcher #
#### Watcher.py ####
This is a Sopel Bot plugin designed to watch only the pages you want to report changes on. Easy as pie commands.

#### Watcher2.py ####
Slightly more complicated in that it will allow you to follow a certain page in the same namespace on all projects.
For example, if you wished, you could follow \<User namespace\>:YourAccount on all projects, regardless of the language.

## Watch Commands ##

```!watch add simplewiki Wikipedia:Vandalism in progress```  
This command would result in changes to Wikipedia:Vandalism in progress on simple.wikipedia.org being reported in the current channel.

```watch del simplewiki Wikipedia:Vandalism in progress```  
This command would result in changes to Wikipedia:Vandalism in progress on simple.wikipedia.org no longer being reported in the current channel.

```!watch ping on enwiki Some Article```  
Add a ping to a watch report for the indicated page. In other words, the bot will specifically mention your IRC nick.

```!watch ping off enwiki Some Article```  
This will make the bot stop mentioning your nick during reports.

```!hush``` / ```!mute```  
Temporarily stop all commands to this channel. The bot will snitch who hushed it. Useful during mass actions.

```!speak```  
Resume reporting changes to the channel.

## Global Watch Commands ##
```!globalwatch {action} {namespaceID} {title}```  
General for of commands

```!globalwatch add 0 Main Page```  
Adds the page called "Main Page" in 0 namespace (Article) to global watch.

```!globalwatch del 3 Operator873```  
Stops following global changes to Operator873's talk page (3 is User talk)

```!globalwatch ping on 0 Main Page```  
Adds a ping (nick mention) to the global watch of "Main Page"

```!globalwatch ping off 0 Main Page```  
Removes the ping from the global watch of "Main Page"
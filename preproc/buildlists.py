#!/usr/bin/python
import json, glob, urllib, os, urllib2,csv,StringIO,re, sys
from pprint import pprint
from urlparse import urlparse

import socket
socket.setdefaulttimeout(400) # Seconds. Loading Bugzilla searches can be slow

if os.path.exists('/home/hallvors/lib'): # custom path for tldextract module on hallvord.com host.
    sys.path.insert(1, '/home/hallvors/lib/tldextract-1.2-py2.6.egg') # TODO: remove or fix this for people.mozilla :)
import tldextract

os.chdir(os.path.dirname(os.path.abspath(__file__))) # For CRON usage..
# We generally want to handle the main domains (i.e. google.com for www.google.com) instead of the full host names
# however, for some major sites with lots of distinct properties we loose too much useful information if we classify it just by domain name..
# conf['subdomainsWeWant'] is a list of hostnames that should not be reduced to domain names. For these, we'll strip any *www.* prefix, but
# no other subdomains
conf = { 'weWantSubdomainsFor': r'(\.google\.com|\.live\.com|\.yahoo\.com|\.js$)' } # the latter is not, strictly speaking, a subdomain..

# http://stackoverflow.com/questions/8230315/python-sets-are-not-json-serializable :-(
class SetEncoder(json.JSONEncoder):
    def default(self, obj):
       if isinstance(obj, set):
          return list(obj)
       return json.JSONEncoder.default(self, obj)

f = open('data/aliases.json')
aliases = json.load(f)
f.close()


def main():
	urltemplate = 'https://api-dev.bugzilla.mozilla.org/latest/bug?component=Mobile&product=Tech%20Evangelism&include_fields=id,summary,creation_time,last_change_time,status,resolution,depends_on,whiteboard,cf_last_resolved,url,priority,flags'
	outputfn = 'test-output'
	pprint('Getting '+urltemplate)
	req = urllib2.Request(urltemplate)
	req.add_header('Accept', 'application/json')
#	req.add_header('User-agent', 'Mozilla/5.0 (Windows NT 5.1; rv:27.0) Gecko/20100101 Firefox/27.0')
	if 1 : # get data from bugzilla (slow..)
		bzresponse = urllib2.urlopen(req, None, 120)
		bzdata = bzresponse.read()
		bzdataobj = json.loads(bzdata)
		print 'Writing '+outputfn+'.json'
		f = open('./data/bugzilla/'+outputfn+'.json', 'w')
		f.write(json.dumps(bzdataobj, indent=2))
		f.close()
	else :
		#TEMPORARY code to speed up testing:
		f = open('./data/bugzilla/'+outputfn+'.json', 'r')
		bzdataobj = json.load(f)
		f.close()

	masterBugTable = {'hostIndex':{}, 'bugs':{}, 'lists':{}}
	for fn in glob.glob('../data/*.json'):
		f = open(fn)
		data = json.load(f)
		match = re.search(r'/data/(.*)\.json$', fn, re.I)
		if match :
			listname = match.groups()[0]
			masterBugTable['lists'][listname] = data
		f.close()

	metrics={'allOpenBugsForAllLists':set(), 'hostsWithOpenBugs':set(), 'totalUniqueHosts':set()}

	for bug in bzdataobj['bugs'] :
		if re.search(r'\[meta\]', bug['summary'], re.I) : # We don't care about [meta] stuff. Why? Well, we're post-post-modern, that's why.
			continue
		masterBugTable['bugs'][bug['id']] = bug;
		# extract host names:
		hostnames = set()
		if 'url' in bug :
			hostnames = hostsFromText(bug['url']) # extract host name from URL field
		if 'summary' in bug :
			hostnames = hostnames.union(hostsFromText(bug['summary'])) # ...and extract host name(s) from summary
		#
		for host in hostnames :
			if not host in masterBugTable['hostIndex'] :
				masterBugTable['hostIndex'][host] = {'open':[], 'resolved':[]}
				metrics['totalUniqueHosts'].add(host)

			if bug['status'] in ['RESOLVED', 'CLOSED', 'VERIFIED'] :
				masterBugTable['hostIndex'][host]['resolved'].append(bug['id'])
			else :
				masterBugTable['hostIndex'][host]['open'].append(bug['id'])
				metrics['allOpenBugsForAllLists'].add(bug['id'])
				metrics['hostsWithOpenBugs'].add(host)
			# Done looking at bug status, updating structures and calculating metrics
		# Done processing each host mentioned for this bug
	# Done processing all bugs in the data dump, one at a time

	# Calculate metrics
	masterBugTable['metrics'] = {"numOpenBugs":len(metrics['allOpenBugsForAllLists']), "numHosts":len(metrics['totalUniqueHosts']), "numHostsWithOpenBugs":len(metrics['hostsWithOpenBugs'])}
	# Write a JS(ON) file
	print 'Writing '+outputfn+'.js'
	f = open('./data/bugzilla/'+outputfn+'.js', 'w')
	f.write('/* This file is generated by preproc/buildlists.py - do not edit */\nvar masterBugTable = '+json.dumps(masterBugTable, indent=2, cls=SetEncoder))
	f.close()
	return;

def hostsFromText(text):
	#  We need to extract any hosts names mentioned in
	#    a) URL field
	#    b) Summary
	#    c) Alias words from aliases.json (i.e. "Hotmail" in summary -> file under live.com)
	#  Also, we want domain names without subdomains (no www. or m. prefixes, for example)
	#  This is a generic method to extract one or more domain names from a text string - the argument can be a URL or some text with a host name mentioned
	text = text.strip().lower()
	hosts = []
	text = re.split('\s', text)
	for word in text :
		word = word.strip('.()!?,[]') # make sure we don't assume a random 'foo.' is a domain due to a sentence-delimiting dot in summary.. Also removing some other characters that might be adjacent..
		if '.' in word: # now go on to assume the first white-space separated string that contains at least one internal period is a domain name
			hosts.append(word)
		else : #
			for hostname in aliases :
				if aliases[hostname] in word :
					#print ('alias match '+hostname+' in '+word+' '+' '.join(text))
					hosts.append(hostname)
	# now we've listed any words/character sequences that contain internal dots.
	# However, we do not want www. or m. or similar prefixes, so we'll run through the list and use
	# tldextract to remove those
	uniquehosts = set()
	for hostname in hosts :
		parts = tldextract.extract(hostname)
		if re.search(conf['weWantSubdomainsFor'], hostname, re.I) and not re.search('^www', parts[0]) :
			hostname = '.'.join( parts[0:3])
		else :
			hostname = '.'.join( parts[1:3])

		uniquehosts.add(hostname)

	# That's it! (We hope..)
	return uniquehosts

if __name__ == "__main__":
    main()
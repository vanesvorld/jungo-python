#!/usr/bin/env python
#
# Copyright 2008 (C) Jose Vasconcellos <jvasco@verizon.net>
#
# A script that can communicate with jungo-based routers
# (such as MI424-WR, USR8200 and WRV54G to backup the installed
# firmware and replace the boot loader.
#
# Tested with Python 2.5 on Linux and Windows
#
"""Usage: %s [options] <IP_address> [redboot.bin]
Valid options:
\t-h | --help: usage statement
\t-d | --no-dump: don't create a flash dump
\t-f | --file: use <filename> to store dump contents
\t-u | --user: provide username (default admin)
\t-p | --pass: provide password (default password1)
\t-P | --proto: set transfer protocol (default tftp)
\t-s | --server: IP address of tftp server
\t-w | --write: initiate loading of redboot (default no modification to flash)
\t-v | --verbose: display additional information
\t-V | --version: display version information
"""

import os
import sys
import getopt
import getpass
import telnetlib
import string
import binascii
import socket
import thread
import SocketServer
import SimpleHTTPServer

server = ""
HOST = "192.168.1.1"
PORT = 8080
user = "admin"
#password = getpass.getpass()
password = "password1"
proto = "http"
imagefile = "redboot.bin"
dumpfile = ""
verbose = 0
no_dump = 0
dumplen = 0x10000
write_image = 0
flashsize=8*1024*1024

####################

def start_server():
    httpd = SocketServer.TCPServer((server,PORT),SimpleHTTPServer.SimpleHTTPRequestHandler)
    thread.start_new_thread(httpd.serve_forever,())

####################

def get_flash_size():
    tn.write("cat /proc/mtd\n")
    # wait for prompt
    buf = tn.read_until("Returned 0", 3)
    if buf:
        i = buf.find('mtd0:')
        if i > 0:
            flashsize = int(buf[i+6:].split()[0],16)

def image_dump(tn, dumpfile):
    if not dumpfile:
        tn.write("ver\n");
        buf = tn.read_until("Returned 0")
        i = buf.find("Platform:")
        if i < 0:
	    platform="jungo"
	else:
	    platform=buf[i+9:].split()[0]

        tn.write("ifconfig br0\n");
        buf = tn.read_until("Returned 0")

        i = buf.find("MAC=")
        if i < 0:
            print "No MAC address found! (use -f option)"
            sys.exit(1)
        dumpfile = "%s-%s.bin" % (platform, buf[i+4:i+21].replace(':',''))
    else:
        tn.write("\n")

    print "Dumping flash contents (%dMB) to %s\n" % (flashsize/1048576, dumpfile)
    f = open(dumpfile, "wb")

    for addr in range(flashsize/dumplen):
	if verbose:
	    sys.stdout.write('.')
	    sys.stdout.flush()

        tn.write("flash_dump -r 0x%x -l %d -4\n" % (addr*dumplen, dumplen))
	tn.read_until("\n")

	count = addr*dumplen
        while 1:
            buf = tn.read_until("\n")
            if buf.strip() == "Returned 0":
                break
            s = buf.split()
            if s and s[0][-1] == ':':
		a=int(s[0][:-1],16)
		if a != count:
		    print "Format error: %x != %x"%(a,count)
		    sys.exit(2)
	    	count += 16
		f.write(binascii.a2b_hex(string.join(s[1:],'')))
	tn.read_until(">",1)

    f.close()

def telnet_option(sock,cmd,option):
    #print "Option: %d %d" % (ord(cmd), ord(option))
    if cmd == telnetlib.DO:
        c=telnetlib.WILL
    elif cmd == telnetlib.WILL:
        c=telnetlib.DO
    sock.sendall(telnetlib.IAC + c + option)

def telnet_timeout():
    print "Fatal error: telnet timeout!"
    sys.exit(1)

def usage():
    print __doc__ % os.path.basename(sys.argv[0])

####################

try:
    opts, args = getopt.getopt(sys.argv[1:], "hdf:u:p:P:s:vVw", \
	["help", "dump", "file=", "user=", "pass=", "proto=","server=", "verbose", "version", "write"])
except getopt.GetoptError:
    # print help information and exit:
    usage()
    sys.exit(1)

for o, a in opts:
    if o in ("-h", "--help"):
	usage()
	sys.exit(1)
    if o in ("-V", "--version"):
	print "%s: 0.6" % sys.argv[0]
	sys.exit(1)
    if o in ("-d", "--no-dump"):
	no_dump = 1
    if o in ("-f", "--file"):
	dumpfile = a
    if o in ("-s", "--server"):
	server = a
    if o in ("-u", "--user"):
	user = a
    if o in ("-p", "--pass"):
	password = a
    if o in ("-P", "--proto"):
	proto = a
    if o in ("-w", "--write"):
	write_image = 1
    if o in ("-v", "--verbose"):
	verbose = 1

# make sure we have enough arguments
if len(args) > 0:
    HOST = args[0]

if len(args) == 2:
    imagefile = args[1]

####################
# create a telnet session to the router
try:
    tn = telnetlib.Telnet(HOST)
except socket.error, msg:
    print "Unable to establish telnet session to %s: %s" % (HOST, msg)
    sys.exit(1)

tn.set_option_negotiation_callback(telnet_option)

buf = tn.read_until("Username: ", 3)
if not buf:
    telnet_timeout()
tn.write(user+"\n")
if password:
    buf = tn.read_until("Password: ", 3)
    if not buf:
        telnet_timeout()
    tn.write(password+"\n")

# wait for prompt
buf = tn.read_until("> ", 3)
if not buf:
    telnet_timeout()

get_flash_size()

if not no_dump:
    image_dump(tn, dumpfile)

# write image file image
if not server:
    server = tn.get_socket().getsockname()[0]
if proto == "http":
    cmd = "load -u %s://%s:%d/%s -r 0\n" % (proto, server, PORT, imagefile)
else:
    cmd = "load -u %s://%s/%s -r 0\n" % (proto, server, imagefile)
print cmd
if write_image:
    if proto == "http":
        start_server()

    tn.write("unlock 0 0x%x\n" % flashsize)
    buf = tn.read_until("Returned 0")

    tn.write(cmd)
    buf = tn.read_until("Returned 0")

tn.write("exit\n")
tn.close()

#!/usr/bin/python3

import os
import sys

from fildem.command import main as command_main

def main():
	if sys.path[0] != '':
		os.chdir(sys.path[0])

	if os.environ.get('XDG_SESSION_TYPE', '').lower() != 'x11':
		# Fildem's legacy Gtk.ApplicationWindow helper requires Xwayland.
		# Native Wayland cannot create this popup correctly with the current
		# GTK implementation.
		os.environ['GDK_BACKEND'] = 'x11'

	os.environ['UBUNTU_MENUPROXY'] = '0'
	command_main()
	
if __name__ == '__main__':
	main()

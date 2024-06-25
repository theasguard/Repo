# -*- coding: utf-8 -*-

'''
	Orion Addon

	THE BEERWARE LICENSE (Revision 42)
	Orion (orionoid.com) wrote this file. As long as you retain this notice you
	can do whatever you want with this stuff. If we meet some day, and you think
	this stuff is worth it, you can buy me a beer in return.
'''

from fenom.sourcesdir.orionoid import Orionoid

class source(Orionoid):

	def __init__(self):
		Orionoid.__init__(self, type = Orionoid.TypeHoster)

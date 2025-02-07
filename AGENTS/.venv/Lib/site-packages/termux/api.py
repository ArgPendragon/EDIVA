from subprocess import call

def copy(text):
	"""copies the text to the clipboard"""
	if text is not None:
		command = f"termux-clipboard-set {text}"
		call(command, shell=True)
		return True
	else:
		return False
		pass


def wifi(on=None):
	"""lets you change wifi status, you can turn it on/off"""
	if on is True:
		command = "termux-wifi-enable true"
		call(command, shell=True)
		return True
	elif on is False:
		command = "termux-wifi-enable false"
		call(command, shell=True)
		return True
	else:
		return False
		pass

def torch(on=None):
	"""lets you turn on/off the torch (flashlight) of the phone"""
	if on is True:
		command = "termux-torch on"
		call(command, shell=True)
		return True
	elif on is False:
		command = "termux-torch off"
		call(command, shell=True)
		return True
	else:
		return False
				

def toast(text, s=None, attr=None):
	"""lets you display a toast message to the user's phone"""
	attrs_list = ['top',
	'middle',
	'bottom']
	if s == True:
		if attr is not None:
			if attr in attrs_list:
				command = f"termux-toast -s -g {attr} {text}"
				call(command, shell=True)
				return True
		else:
			command = f"termux-toast -s {text}"
			call(command, shell=True)
			return True
	else:
		if attr is not None:
			if attr in attrs_list:
				command = f"termux-toast -g {attr} {text}"
			call(command, shell=True)
			return True
		else:
			command = f"termux-toast {text}"
			call(command, shell=True)
			return True
	if attr is not None:
		if attr in attrs_list:
			command = f"termux-toast -g {attr} {text}"
			call(command, shell=True)
			return True
		else:
			attr=None
			return True